#!/usr/bin/env python3
# graph_results.py  —  run after the bash script completes

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import os

OUTPUT_DIR = "./ab_results"
GRAPH_DIR  = "./ab_graphs"
os.makedirs(GRAPH_DIR, exist_ok=True)

summary = pd.read_csv(f"{OUTPUT_DIR}/summary.csv")
req_csv = pd.read_csv(f"{OUTPUT_DIR}/all_requests.csv")

# ── 1. Latency percentiles per source IP (p50 / p95 / p99) ───────────────────
fig, ax = plt.subplots(figsize=(18, 5))
x = np.arange(len(summary))
w = 0.25
ax.bar(x - w, summary["p50_ms"],  w, label="p50",  color="#4C9BE8")
ax.bar(x,      summary["p95_ms"], w, label="p95",  color="#F5A623")
ax.bar(x + w,  summary["p99_ms"], w, label="p99",  color="#E84C4C")
ax.set_xticks(x)
ax.set_xticklabels(summary["source_ip"], rotation=90, fontsize=6)
ax.set_ylabel("Latency (ms)")
ax.set_title("Latency Percentiles per Source IP")
ax.legend()
fig.tight_layout()
fig.savefig(f"{GRAPH_DIR}/latency_per_ip.png", dpi=150)
plt.close()

# ── 2. Requests per second per source IP ─────────────────────────────────────
fig, ax = plt.subplots(figsize=(18, 4))
ax.bar(summary["source_ip"], summary["rps"], color="#4CE8A0")
ax.set_xticklabels(summary["source_ip"], rotation=90, fontsize=6)
ax.set_ylabel("Requests/sec")
ax.set_title("Throughput per Source IP")
fig.tight_layout()
fig.savefig(f"{GRAPH_DIR}/rps_per_ip.png", dpi=150)
plt.close()

# ── 3. Failed requests per source IP ─────────────────────────────────────────
fig, ax = plt.subplots(figsize=(18, 4))
ax.bar(summary["source_ip"], summary["failed_requests"], color="#E84C4C")
ax.set_xticklabels(summary["source_ip"], rotation=90, fontsize=6)
ax.set_ylabel("Failed Requests")
ax.set_title("Failed Requests per Source IP")
fig.tight_layout()
fig.savefig(f"{GRAPH_DIR}/failures_per_ip.png", dpi=150)
plt.close()

# ── 4. Aggregate latency CDF across all IPs ───────────────────────────────────
# all_requests.csv has percentile rows — pivot to get one CDF line per IP
# then plot the overall aggregate
pivot = req_csv.pivot_table(index="percentage", values="time_ms", aggfunc="mean")
fig, ax = plt.subplots(figsize=(10, 5))
ax.plot(pivot["time_ms"], pivot.index, color="#4C9BE8", linewidth=2)
ax.set_xlabel("Latency (ms)")
ax.set_ylabel("Percentile (%)")
ax.set_title("Aggregate Latency CDF (mean across all IPs)")
ax.grid(True, alpha=0.3)
fig.tight_layout()
fig.savefig(f"{GRAPH_DIR}/latency_cdf.png", dpi=150)
plt.close()

# ── 5. Transfer rate heatmap (IPs as y-axis, single metric as color) ─────────
fig, ax = plt.subplots(figsize=(6, 10))
vals = summary["transfer_rate_kbps"].values.reshape(-1, 1)
im = ax.imshow(vals, aspect="auto", cmap="YlOrRd")
ax.set_yticks(range(len(summary)))
ax.set_yticklabels(summary["source_ip"], fontsize=6)
ax.set_xticks([])
ax.set_title("Transfer Rate (KB/s) per IP")
plt.colorbar(im, ax=ax, label="KB/s")
fig.tight_layout()
fig.savefig(f"{GRAPH_DIR}/transfer_heatmap.png", dpi=150)
plt.close()

print(f"Graphs saved to {GRAPH_DIR}/")
print("  latency_per_ip.png   — p50/p95/p99 bar chart")
print("  rps_per_ip.png       — throughput per IP")
print("  failures_per_ip.png  — failed requests per IP")
print("  latency_cdf.png      — aggregate CDF curve")
print("  transfer_heatmap.png — transfer rate heatmap")