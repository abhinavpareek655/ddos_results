#!/usr/bin/env python3
"""
autoscaler.py  –  HAProxy autoscaler
Metrics for CPU / memory / disk / network are fetched from each backend
server's own metrics_agent.py  (port 9101).
HAProxy-side metrics (active connections) come from the local socket.
"""

import socket
import time
import logging
import urllib.request
import json
import csv
import os
from datetime import datetime

HAPROXY_SOCKET       = "/run/haproxy/admin.sock"
BACKEND_NAME         = "my_backend"
POLL_INTERVAL        = 2
SCALE_UP_THRESHOLD   = 70
SCALE_DOWN_THRESHOLD = 30
COOLDOWN             = 30
SCALING_ENABLED      = True
AGENT_PORT           = 9101
MAX_WEIGHT           = 256
MIN_WEIGHT           = 1
METRICS_FILE         = "/var/log/haproxy-metrics.csv"
DISK_MAX_MB_S        = 334
NET_MAX_MB_S         = 125
CONN_MAX             = 1000

SERVERS = [
    {"name": "server1", "ip": "192.168.100.4"},
    {"name": "server2", "ip": "192.168.100.5"},
    {"name": "server3", "ip": "192.168.100.6"},
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("autoscaler")

# ── HAProxy helpers ───────────────────────────────────────────────────────────

def ha_cmd(cmd):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.settimeout(5)
        s.connect(HAPROXY_SOCKET)
        s.sendall((cmd + "\n").encode())
        data = b""
        while True:
            chunk = s.recv(4096)
            if not chunk:
                break
            data += chunk
        return data.decode().strip()


def is_server_up(name):
    for line in ha_cmd("show servers state " + BACKEND_NAME).splitlines():
        parts = line.split()
        if len(parts) >= 6 and parts[3] == name:
            return parts[5] == "2"
    return False

def calculate_load(data):
    cpu    = data.get("cpu", 0)
    mem    = data.get("mem_usage_pct", 0)
    disk_r = min(data.get("disk_read_mb_s",  0) / DISK_MAX_MB_S * 100, 100)
    disk_w = min(data.get("disk_write_mb_s", 0) / DISK_MAX_MB_S * 100, 100)
    net_rx = min(data.get("net_rx_mb_s",     0) / NET_MAX_MB_S  * 100, 100)
    net_tx = min(data.get("net_tx_mb_s",     0) / NET_MAX_MB_S  * 100, 100)
    conns  = min(data.get("established",     0) / CONN_MAX      * 100, 100)

    return round(
        cpu    * 0.40 +
        mem    * 0.25 +
        disk_w * 0.10 +
        conns  * 0.10 +
        disk_r * 0.05 +
        net_rx * 0.05 +
        net_tx * 0.05,
        2
    )

def set_server(name, enable):
    state = "ready" if enable else "maint"
    ha_cmd("set server " + BACKEND_NAME + "/" + name + " state " + state)
    log.info("%s -> %s", name, "enabled" if enable else "disabled")


def set_weight(name, weight):
    weight = max(MIN_WEIGHT, min(MAX_WEIGHT, weight))
    ha_cmd("set server " + BACKEND_NAME + "/" + name + " weight " + str(weight))
    log.info("%s weight=%d", name, weight)


def get_active_connections():
    total = 0
    for line in ha_cmd("show stat").splitlines():
        parts = line.split(",")
        if len(parts) > 4 and parts[0] == BACKEND_NAME and parts[1] not in ("BACKEND", "FRONTEND"):
            try:
                total += int(parts[4])
            except ValueError:
                pass
    return total

# ── Agent metrics fetch ───────────────────────────────────────────────────────

# All fields the agent exposes (must match metrics_agent.py payload keys)
AGENT_FIELDS = [
    "cpu", "mem",
    "mem_used_mb", "mem_total_mb", "mem_usage_pct", "buffers_mb", "cached_mb",
    "disk_read_mb_s", "disk_write_mb_s",
    "disk_used_gb", "disk_total_gb", "disk_usage_pct",
    "net_rx_mb_s", "net_tx_mb_s",
    "total_connections", "established", "syn_recv", "time_wait", "close_wait",
]

_EMPTY_AGENT = {f: "" for f in AGENT_FIELDS}


def fetch_agent(ip):
    """Fetch full metrics dict from one backend agent. Returns None on failure."""
    try:
        url = f"http://{ip}:{AGENT_PORT}/metrics"
        with urllib.request.urlopen(url, timeout=3) as r:
            return json.loads(r.read())
    except Exception as e:
        log.warning("could not reach agent at %s: %s", ip, e)
        return None


def collect_server_metrics():
    """
    Returns a list of dicts – one per *up* server – containing:
      name, ip, load (for scaling logic), and all agent fields.
    Servers that are down or unreachable get an empty-field entry so the
    CSV row is never blank.
    """
    results = []
    for srv in SERVERS:
        up   = is_server_up(srv["name"])
        data = fetch_agent(srv["ip"]) if up else None

        if data is not None:
            load = calculate_load(data)
            log.info("%s load=%.1f%% (cpu=%.1f mem=%.1f)",
                     srv["name"], load, data.get("cpu", 0), data.get("mem", 0))
            entry = {"name": srv["name"], "ip": srv["ip"], "load": load, "up": True}
            entry.update({f: data.get(f, 0) for f in AGENT_FIELDS})
        else:
            entry = {"name": srv["name"], "ip": srv["ip"], "load": None, "up": False}
            entry.update(_EMPTY_AGENT)

        results.append(entry)
    return results


def update_weights(active):
    """active = entries from collect_server_metrics() where up=True."""
    if not active:
        return
    scores = [{"name": s["name"], "score": max(0, 100 - s["load"])} for s in active]
    total  = sum(s["score"] for s in scores)
    if total == 0:
        for s in scores:
            set_weight(s["name"], MIN_WEIGHT)
        return
    for s in scores:
        weight = int((s["score"] / total) * MAX_WEIGHT)
        set_weight(s["name"], weight)

# ── CSV ───────────────────────────────────────────────────────────────────────

# One group of agent columns per server
def _server_col(srv_name, field):
    return f"{srv_name}_{field}"

def build_csv_fields():
    fields = ["timestamp", "haproxy_active_conns"]
    for srv in SERVERS:
        fields.append(f"{srv['name']}_up")
        for f in AGENT_FIELDS:
            fields.append(_server_col(srv["name"], f))
    fields.append("avg_load_pct")
    return fields

CSV_FIELDS = build_csv_fields()


def open_csv():
    exists = os.path.isfile(METRICS_FILE)
    f      = open(METRICS_FILE, "a", newline="")
    writer = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
    if not exists:
        writer.writeheader()
    return f, writer

# ── Main loop ─────────────────────────────────────────────────────────────────

def run():
    last_action = 0.0
    log.info("autoscaler started. server1 always on. server2/3 dynamic.")
    log.info("scale up > %d%% | scale down < %d%%", SCALE_UP_THRESHOLD, SCALE_DOWN_THRESHOLD)
    log.info("metrics logging to %s", METRICS_FILE)

    csv_file, writer = open_csv()

    try:
        while True:
            try:
                now      = time.time()
                ha_conns = get_active_connections()
                servers  = collect_server_metrics()

                active   = [s for s in servers if s["up"] and s["load"] is not None]
                avg      = sum(s["load"] for s in active) / len(active) if active else None
                s2_up    = next((s["up"] for s in servers if s["name"] == "server2"), False)
                s3_up    = next((s["up"] for s in servers if s["name"] == "server3"), False)
                cooled   = (now - last_action) >= COOLDOWN

                if not active:
                    log.warning("no active servers with load data, skipping scale logic")
                elif SCALING_ENABLED:
                    log.info("avg=%.1f%% server2=%s server3=%s ha_conns=%d",
                             avg, "UP" if s2_up else "DOWN",
                             "UP" if s3_up else "DOWN", ha_conns)

                    update_weights(active)

                    if cooled:
                        if avg > SCALE_UP_THRESHOLD:
                            if not s2_up:
                                set_server("server2", True);  last_action = now
                            elif not s3_up:
                                set_server("server3", True);  last_action = now
                        elif avg < SCALE_DOWN_THRESHOLD:
                            if s3_up:
                                set_server("server3", False); last_action = now
                            elif s2_up:
                                set_server("server2", False); last_action = now
                    else:
                        log.info("cooldown: %ds remaining",
                                 int(COOLDOWN - (now - last_action)))

                # ── build CSV row ──────────────────────────────────────────
                row = {
                    "timestamp":          datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "haproxy_active_conns": ha_conns,
                    "avg_load_pct":       round(avg, 2) if avg is not None else "",
                }
                for srv in servers:
                    row[f"{srv['name']}_up"] = 1 if srv["up"] else 0
                    for f in AGENT_FIELDS:
                        row[_server_col(srv["name"], f)] = srv.get(f, "")

                writer.writerow(row)
                csv_file.flush()

            except Exception as e:
                log.error("loop error: %s", e, exc_info=True)

            time.sleep(POLL_INTERVAL)

    finally:
        csv_file.close()


if __name__ == "__main__":
    run()
