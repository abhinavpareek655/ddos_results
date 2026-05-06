#!/usr/bin/env python3

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
SCALE_UP_THRESHOLD   = 75
SCALE_DOWN_THRESHOLD = 40
COOLDOWN             = 30
SCALING_ENABLED      = True
AGENT_PORT           = 9101
MAX_WEIGHT           = 256
MIN_WEIGHT           = 1
METRICS_FILE         = "/var/log/haproxy-metrics.csv"

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

# ── Agent load fetch ──────────────────────────────────────────────────────────

def get_load(ip):
    try:
        url = "http://" + ip + ":" + str(AGENT_PORT) + "/metrics"
        with urllib.request.urlopen(url, timeout=3) as r:
            data = json.loads(r.read())
            return max(data["cpu"], data["mem"])
    except Exception as e:
        log.warning("could not reach agent at %s: %s", ip, e)
        return None


def collect_loads():
    results = []
    for srv in SERVERS:
        if not is_server_up(srv["name"]):
            continue
        load = get_load(srv["ip"])
        if load is not None:
            results.append({"name": srv["name"], "ip": srv["ip"], "load": load})
            log.info("%s load=%.1f%%", srv["name"], load)
    return results


def update_weights(loads):
    if not loads:
        return
    scores = [{"name": s["name"], "score": 100 - s["load"]} for s in loads]
    total  = sum(s["score"] for s in scores)
    if total == 0:
        for s in scores:
            set_weight(s["name"], MIN_WEIGHT)
        return
    for s in scores:
        weight = int((s["score"] / total) * MAX_WEIGHT)
        set_weight(s["name"], weight)

# ── System metrics (from /proc) ───────────────────────────────────────────────

prev_cpu = None
prev_net = None
prev_disk = None


def read_file(path):
    try:
        with open(path) as f:
            return f.read()
    except:
        return ""


def get_cpu():
    global prev_cpu
    line = read_file("/proc/stat").split("\n")[0]
    fields = [int(x) for x in line.split()[1:9]]
    if prev_cpu:
        deltas = [fields[i] - prev_cpu[i] for i in range(len(fields))]
        total  = sum(deltas)
        idle   = deltas[3]
        usage  = round(100.0 * (total - idle) / total, 2) if total > 0 else 0.0
    else:
        usage = 0.0
    prev_cpu = fields
    return usage


def get_memory():
    data = {}
    for line in read_file("/proc/meminfo").split("\n"):
        parts = line.split(":")
        if len(parts) == 2:
            data[parts[0].strip()] = int(parts[1].strip().split()[0])
    total     = data.get("MemTotal", 0)
    available = data.get("MemAvailable", 0)
    used      = total - available
    return {
        "mem_used_mb":   round(used / 1024, 2),
        "mem_total_mb":  round(total / 1024, 2),
        "mem_usage_pct": round(100.0 * used / total, 2) if total > 0 else 0.0,
        "buffers_mb":    round(data.get("Buffers", 0) / 1024, 2),
        "cached_mb":     round(data.get("Cached", 0) / 1024, 2),
    }


def get_disk_io():
    global prev_disk
    total_reads = 0
    total_writes = 0
    for line in read_file("/proc/diskstats").split("\n"):
        parts = line.split()
        if len(parts) < 14:
            continue
        dev = parts[2]
        if dev.startswith(("sd", "nvme", "vd", "hd")) and not dev[-1].isdigit():
            total_reads  += int(parts[5])
            total_writes += int(parts[9])
    if prev_disk:
        read_mb  = round((total_reads  - prev_disk["reads"])  * 512 / 1024 / 1024 / POLL_INTERVAL, 2)
        write_mb = round((total_writes - prev_disk["writes"]) * 512 / 1024 / 1024 / POLL_INTERVAL, 2)
    else:
        read_mb = write_mb = 0.0
    prev_disk = {"reads": total_reads, "writes": total_writes}
    return {"disk_read_mb_s": read_mb, "disk_write_mb_s": write_mb}


def get_disk_usage():
    try:
        st = os.statvfs("/")
        total = st.f_blocks * st.f_frsize / 1024 / 1024 / 1024
        free  = st.f_bfree  * st.f_frsize / 1024 / 1024 / 1024
        used  = total - free
        return {
            "disk_used_gb":   round(used, 2),
            "disk_total_gb":  round(total, 2),
            "disk_usage_pct": round(100.0 * used / total, 2) if total > 0 else 0.0,
        }
    except:
        return {"disk_used_gb": 0, "disk_total_gb": 0, "disk_usage_pct": 0}


def get_network():
    global prev_net
    total_rx = total_tx = 0
    for line in read_file("/proc/net/dev").split("\n")[2:]:
        if not line or ":" not in line:
            continue
        iface, stats = line.split(":")
        if iface.strip() == "lo":
            continue
        parts = stats.split()
        if len(parts) < 16:
            continue
        total_rx += int(parts[0])
        total_tx += int(parts[8])
    if prev_net:
        rx_mb = round((total_rx - prev_net["rx"]) / 1024 / 1024 / POLL_INTERVAL, 2)
        tx_mb = round((total_tx - prev_net["tx"]) / 1024 / 1024 / POLL_INTERVAL, 2)
    else:
        rx_mb = tx_mb = 0.0
    prev_net = {"rx": total_rx, "tx": total_tx}
    return {"net_rx_mb_s": rx_mb, "net_tx_mb_s": tx_mb}


def get_connections():
    state_map = {
        "01": "ESTABLISHED", "02": "SYN_SENT", "03": "SYN_RECV",
        "04": "FIN_WAIT1",   "05": "FIN_WAIT2", "06": "TIME_WAIT",
        "07": "CLOSE",       "08": "CLOSE_WAIT", "09": "LAST_ACK",
        "0A": "LISTEN",      "0B": "CLOSING"
    }
    counts = {v: 0 for v in state_map.values()}
    for src in ("/proc/net/tcp", "/proc/net/tcp6"):
        for line in read_file(src).split("\n")[1:]:
            parts = line.split()
            if len(parts) >= 4:
                state = state_map.get(parts[3])
                if state:
                    counts[state] += 1
    return {
        "total_connections": sum(counts.values()),
        "established":       counts["ESTABLISHED"],
        "syn_recv":          counts["SYN_RECV"],
        "time_wait":         counts["TIME_WAIT"],
        "close_wait":        counts["CLOSE_WAIT"],
    }


def collect_system_metrics():
    m = {"timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    m["cpu_usage_pct"] = get_cpu()
    m.update(get_memory())
    m.update(get_disk_io())
    m.update(get_disk_usage())
    m.update(get_network())
    m.update(get_connections())
    return m

# ── CSV writer ────────────────────────────────────────────────────────────────

CSV_FIELDS = [
    "timestamp", "cpu_usage_pct",
    "mem_used_mb", "mem_total_mb", "mem_usage_pct", "buffers_mb", "cached_mb",
    "disk_read_mb_s", "disk_write_mb_s",
    "disk_used_gb", "disk_total_gb", "disk_usage_pct",
    "net_rx_mb_s", "net_tx_mb_s",
    "total_connections", "established", "syn_recv", "time_wait", "close_wait",
    "haproxy_active_conns", "server2_up", "server3_up", "avg_load_pct",
]


def open_csv():
    exists = os.path.isfile(METRICS_FILE)
    f = open(METRICS_FILE, "a", newline="")
    writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
    if not exists:
        writer.writeheader()
    return f, writer

# ── Main loop ─────────────────────────────────────────────────────────────────

def run():
    last_action = 0.0
    log.info("autoscaler started. server1 always on. server2/3 dynamic.")
    log.info("scale up > %d%% | scale down < %d%%", SCALE_UP_THRESHOLD, SCALE_DOWN_THRESHOLD)
    log.info("metrics logging to %s", METRICS_FILE)

    # warm up /proc counters
    get_cpu(); get_network(); get_disk_io()

    csv_file, writer = open_csv()

    try:
        while True:
            try:
                sys_metrics  = collect_system_metrics()
                loads        = collect_loads()
                s2_up        = is_server_up("server2")
                s3_up        = is_server_up("server3")
                ha_conns     = get_active_connections()
                now          = time.time()
                cooled       = (now - last_action) >= COOLDOWN

                avg = sum(s["load"] for s in loads) / len(loads) if loads else None

                if not loads:
                    log.warning("no load data available, skipping scale logic")
                elif SCALING_ENABLED:
                    log.info("avg=%.1f%% server2=%s server3=%s ha_conns=%d",
                             avg, "UP" if s2_up else "DOWN", "UP" if s3_up else "DOWN", ha_conns)

                    update_weights(loads)

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
                        log.info("cooldown: %ds remaining", int(COOLDOWN - (now - last_action)))

                row = sys_metrics
                row["haproxy_active_conns"] = ha_conns
                row["server2_up"]           = 1 if s2_up else 0
                row["server3_up"]           = 1 if s3_up else 0
                row["avg_load_pct"]         = round(avg, 2) if avg is not None else ""
                writer.writerow(row)
                csv_file.flush()

            except Exception as e:
                log.error("error: %s", e)

            time.sleep(POLL_INTERVAL)

    finally:
        csv_file.close()


if __name__ == "__main__":
    run()