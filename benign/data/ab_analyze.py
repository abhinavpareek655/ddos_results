#!/usr/bin/env python3
"""
AB Results Analyzer â€” handles full runs, partial runs, and txt-only
Usage:
  python3 ab_analyze.py <file.csv> <file.dat> <file.txt>
  python3 ab_analyze.py <file.txt>          # txt only
  python3 ab_analyze.py                     # auto-detect in current dir
"""

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import numpy as np
import re, sys, os, glob

# â”€â”€ File loading â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def load_csv(path):
    try:
        df = pd.read_csv(path)
        if df.empty or len(df.columns) < 2:
            return None
        df.columns = ["percentage", "time_ms"]
        df = df.dropna()
        df["time_ms"] = pd.to_numeric(df["time_ms"], errors="coerce")
        df = df.dropna()
        return df if len(df) > 1 else None
    except Exception:
        return None

def load_dat(path):
    try:
        df = pd.read_csv(path, sep="\t")
        if df.empty or len(df) < 1:
            return None
        df.columns = ["starttime", "seconds", "ctime", "dtime", "ttime", "wait"]
        for col in ["seconds", "ctime", "dtime", "ttime", "wait"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df.dropna()
        if df.empty:
            return None
        df = df.sort_values("seconds").reset_index(drop=True)
        df["elapsed"] = df["seconds"] - df["seconds"].min()
        return df
    except Exception:
        return None

def parse_txt(path):
    text = open(path).read()

    # Detect incomplete run
    incomplete = bool(re.search(r"Total of \d+ requests completed", text))

    def g(pattern, cast=str, default="N/A"):
        m = re.search(pattern, text)
        if m:
            try: return cast(m.group(1).strip())
            except: return default
        return default

    # Extract completed count from incomplete message too
    completed_partial = None
    m = re.search(r"Total of (\d+) requests completed", text)
    if m:
        completed_partial = int(m.group(1))

    stats = {
        "incomplete":   incomplete,
        "host":         g(r"Server Hostname:\s+(.+)"),
        "port":         g(r"Server Port:\s+(\d+)"),
        "path":         g(r"Document Path:\s+(.+)"),
        "concurrency":  g(r"Concurrency Level:\s+(\d+)", int, "N/A"),
        "total_time_s": g(r"Time taken for tests:\s+([\d.]+)", float, 0),
        "total_req":    g(r"Complete requests:\s+(\d+)", int, completed_partial or 0),
        "failed_req":   g(r"Failed requests:\s+(\d+)", int, 0),
        "non2xx":       g(r"Non-2xx responses:\s+(\d+)", int, 0),
        "rps":          g(r"Requests per second:\s+([\d.]+)", float, "N/A"),
        "mean_ms":      g(r"Time per request:\s+([\d.]+) \[ms\] \(mean\)\n", float, "N/A"),
        "transfer_kbs": g(r"Transfer rate:\s+([\d.]+)", float, "N/A"),
        "percentiles":  {},
    }

    for m in re.finditer(r"^\s+(\d+)%\s+(\d+)", text, re.MULTILINE):
        stats["percentiles"][int(m.group(1))] = int(m.group(2))

    return stats

# â”€â”€ Auto-detect â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def find_files():
    csv = glob.glob("*.csv")
    dat = glob.glob("*.dat")
    txt = glob.glob("*.txt")
    if not txt:
        print("No .txt file found.")
        sys.exit(1)
    return (csv[0] if csv else None,
            dat[0] if dat else None,
            txt[0])

# â”€â”€ Theme â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

DARK  = "#ffffff"
PANEL = "#f7f9fc"
GRID  = "#dce3ed"
BLUE  = "#2166ac"
GREEN = "#1a9641"
AMBER = "#d7722c"
RED   = "#b2182b"

def style_ax(ax, title):
    ax.set_facecolor(PANEL)
    ax.set_title(title, color="#111111", fontsize=11, fontweight="bold", pad=10)
    ax.tick_params(colors="#333333", labelsize=9)
    ax.xaxis.label.set_color("#333333")
    ax.yaxis.label.set_color("#333333")
    for spine in ax.spines.values():
        spine.set_edgecolor("#b0bec5")
    ax.grid(color=GRID, linewidth=0.7, alpha=1.0, linestyle="--")

def no_data_panel(ax, title, reason="No data available"):
    ax.set_facecolor(PANEL)
    ax.set_title(title, color="#111111", fontsize=11, fontweight="bold", pad=10)
    for spine in ax.spines.values():
        spine.set_edgecolor("#b0bec5")
    ax.text(0.5, 0.5, reason, transform=ax.transAxes,
            ha="center", va="center", color="#aaaaaa",
            fontsize=11, style="italic")
    ax.set_xticks([])
    ax.set_yticks([])

def ms_label(ms):
    return f"{ms/1000:.1f}s" if ms >= 1000 else f"{ms}ms"

# â”€â”€ Plot â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def plot(csv_path, dat_path, txt_path, out_path="ab_results.png"):
    df_csv = load_csv(csv_path)  if csv_path else None
    df_dat = load_dat(dat_path)  if dat_path else None
    stats  = parse_txt(txt_path)
    pct    = stats["percentiles"]

    has_csv = df_csv is not None
    has_dat = df_dat is not None

    plt.rcParams.update({
        "font.family": "serif",
        "font.serif":  ["DejaVu Serif", "Times New Roman", "Georgia"],
    })

    fig = plt.figure(figsize=(18, 16), facecolor="white")

    title = f"ApacheBench Performance Analysis"
    if stats["host"] != "N/A":
        title += f" â€” {stats['host']}:{stats['port']}{stats['path']}"
    if stats["incomplete"]:
        title += "  [INCOMPLETE RUN]"

    fig.suptitle(title, color="#111111" if not stats["incomplete"] else RED,
                 fontsize=14, fontweight="bold", y=0.98)

    gs = gridspec.GridSpec(3, 2, figure=fig, hspace=0.45, wspace=0.35)

    # â”€â”€ Panel 1: Latency CDF â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    ax1 = fig.add_subplot(gs[0, 0])
    if has_csv:
        ax1.plot(df_csv["time_ms"], df_csv["percentage"], color=BLUE, linewidth=2)
        ax1.fill_betweenx(df_csv["percentage"].astype(float),
                          df_csv["time_ms"].astype(float),
                          alpha=0.15, color=BLUE)
        for p, col in [(50, GREEN), (95, AMBER), (99, RED)]:
            if p in pct:
                ax1.axhline(p, color=col, linewidth=0.9, linestyle="--", alpha=0.8)
                ax1.axvline(pct[p], color=col, linewidth=0.9, linestyle="--", alpha=0.8)
                ax1.text(pct[p], 2, f"p{p}\n{ms_label(pct[p])}",
                         color="#111111", fontsize=7.5, ha="center",
                         bbox=dict(boxstyle="round,pad=0.2", fc="white", ec=col, alpha=0.9))
        ax1.set_xlabel("Latency (ms)")
        ax1.set_ylabel("Percentile (%)")
        style_ax(ax1, "Latency CDF")
    elif pct:
        # Build CDF from percentile dict
        xs = list(pct.values())
        ys = list(pct.keys())
        ax1.plot(xs, ys, color=BLUE, linewidth=2, marker="o", markersize=4)
        ax1.fill_betweenx(ys, xs, alpha=0.15, color=BLUE)
        ax1.set_xlabel("Latency (ms)")
        ax1.set_ylabel("Percentile (%)")
        style_ax(ax1, "Latency CDF (from percentile table)")
    else:
        no_data_panel(ax1, "Latency CDF", "Run incomplete â€” no percentile data")

    # â”€â”€ Panel 2: Percentile bar chart â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    ax2 = fig.add_subplot(gs[0, 1])
    if pct:
        labels   = [f"p{k}" for k in pct]
        values_s = [v / 1000 for v in pct.values()]
        mean_s   = stats["mean_ms"] / 1000 if stats["mean_ms"] != "N/A" else (values_s[len(values_s)//2])
        colors   = [GREEN if v < mean_s * 0.5 else AMBER if v < mean_s * 1.5 else RED
                    for v in values_s]
        bars = ax2.bar(labels, values_s, color=colors, width=0.6, edgecolor="white")
        for bar, val in zip(bars, values_s):
            ax2.text(bar.get_x() + bar.get_width()/2,
                     bar.get_height() + max(values_s)*0.01,
                     f"{val:.0f}s", ha="center", color="#333333", fontsize=8)
        ax2.set_ylabel("Time (seconds)")
        style_ax(ax2, "Response Time by Percentile")
    else:
        no_data_panel(ax2, "Response Time by Percentile", "Run incomplete â€” no percentile data")

    # â”€â”€ Panel 3: Scatter over time â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    ax3 = fig.add_subplot(gs[1, 0])
    if has_dat and len(df_dat) > 0:
        ax3.scatter(df_dat["elapsed"], df_dat["ttime"], s=1.5, alpha=0.25, color=BLUE)
        window  = max(1, len(df_dat) // 80)
        rolling = df_dat["ttime"].rolling(window, min_periods=1).mean()
        ax3.plot(df_dat["elapsed"], rolling, color=AMBER, linewidth=1.8, label="rolling mean")
        if stats["mean_ms"] != "N/A":
            ax3.axhline(stats["mean_ms"], color=RED, linewidth=1, linestyle="--",
                        alpha=0.8, label=f"mean {ms_label(int(stats['mean_ms']))}")
        ax3.set_xlabel("Elapsed Time (s)")
        ax3.set_ylabel("Response Time (ms)")
        ax3.legend(fontsize=8, labelcolor="#111111", facecolor="white", edgecolor="#b0bec5")
        style_ax(ax3, "Response Time Over Test Duration")
    else:
        no_data_panel(ax3, "Response Time Over Test Duration",
                      "No .dat data\n(run was cut off before completion)")

    # â”€â”€ Panel 4: Connect / Wait / Processing â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    ax4 = fig.add_subplot(gs[1, 1])
    if has_dat and len(df_dat) > 0:
        elapsed_range = df_dat["elapsed"].max() - df_dat["elapsed"].min()
        if len(df_dat) < 2 or elapsed_range == 0:
            means = df_dat[["ctime", "wait", "dtime"]].mean()
            ax4.bar(["Connect", "Wait", "Processing"],
                    [means["ctime"], means["wait"], means["dtime"]],
                    color=[GREEN, AMBER, BLUE], alpha=0.85, edgecolor="white", width=0.5)
            ax4.set_ylabel("Time (ms)")
            ax4.set_xlabel("Phase")
            style_ax(ax4, "Connect / Wait / Processing Breakdown")
        else:
            buckets = np.linspace(df_dat["elapsed"].min(), df_dat["elapsed"].max(), 50)
            df_dat["bucket"] = pd.cut(df_dat["elapsed"], buckets, labels=False, duplicates="drop")
            grp = df_dat.groupby("bucket")[["ctime", "dtime", "wait"]].mean()
            x   = grp.index.astype(float)
            ax4.stackplot(x, grp["ctime"], grp["wait"], grp["dtime"],
                          labels=["Connect", "Wait", "Processing"],
                          colors=[GREEN, AMBER, BLUE], alpha=0.85)
            ax4.set_xlabel("Elapsed Time (buckets)")
            ax4.set_ylabel("Time (ms)")
            ax4.legend(fontsize=8, labelcolor="#111111", facecolor="white", edgecolor="#b0bec5")
            style_ax(ax4, "Connect / Wait / Processing Breakdown")
    else:
        # Fall back to connection times from .txt if available
        if stats.get("total_mean") or stats.get("connect_mean") != "N/A":
            phases = ["Connect", "Wait", "Processing"]
            vals   = [
                stats.get("connect_mean", 0) or 0,
                stats.get("waiting_mean", 0) or 0,
                stats.get("processing_mean", 0) or 0,
            ]
            ax4.bar(phases, vals, color=[GREEN, AMBER, BLUE],
                    alpha=0.85, edgecolor="white", width=0.5)
            ax4.set_ylabel("Mean Time (ms)")
            style_ax(ax4, "Connect / Wait / Processing (from .txt)")
        else:
            no_data_panel(ax4, "Connect / Wait / Processing",
                          "No .dat data available")

    # â”€â”€ Panel 5: Histogram â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    ax5 = fig.add_subplot(gs[2, 0])
    if has_dat and len(df_dat) > 1:
        bins = min(60, max(5, len(df_dat) // 5))
        ax5.hist(df_dat["ttime"], bins=bins, color=BLUE, edgecolor="white", alpha=0.9)
        if stats["mean_ms"] != "N/A":
            ax5.axvline(stats["mean_ms"], color=RED, linewidth=1.5, linestyle="--",
                        label=f"mean {ms_label(int(stats['mean_ms']))}")
        if 50 in pct:
            ax5.axvline(pct[50], color=GREEN, linewidth=1.5, linestyle="--",
                        label=f"median {ms_label(pct[50])}")
        ax5.set_xlabel("Response Time (ms)")
        ax5.set_ylabel("Number of Requests")
        ax5.legend(fontsize=8, labelcolor="#111111", facecolor="white", edgecolor="#b0bec5")
        style_ax(ax5, "Response Time Distribution")
    else:
        no_data_panel(ax5, "Response Time Distribution",
                      "No .dat data available")

    # â”€â”€ Panel 6: Summary table â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    ax6 = fig.add_subplot(gs[2, 1])
    ax6.set_facecolor(PANEL)
    ax6.axis("off")
    ax6.set_title("Test Summary", color="#111111", fontsize=11, fontweight="bold", pad=10)

    def fmt(val, suffix=""):
        if val == "N/A" or val is None: return "N/A"
        return f"{val}{suffix}"

    rows = [
        ("Status",           "[INCOMPLETE]" if stats["incomplete"] else "Complete"),
        ("Total Requests",   f"{stats['total_req']:,}" if stats['total_req'] else "N/A"),
        ("Failed Requests",  f"{stats['failed_req']:,}" if stats['failed_req'] != "N/A" else "N/A"),
        ("Non-2xx",          f"{stats['non2xx']:,}" if stats['non2xx'] != "N/A" else "N/A"),
        ("Concurrency",      fmt(stats["concurrency"])),
        ("Test Duration",    f"{stats['total_time_s']:.1f}s" if stats['total_time_s'] else "N/A"),
        ("Requests/sec",     fmt(stats["rps"])),
        ("Mean Latency",     ms_label(int(stats["mean_ms"])) if stats["mean_ms"] != "N/A" else "N/A"),
        ("p50",              ms_label(pct[50])  if 50  in pct else "N/A"),
        ("p95",              ms_label(pct[95])  if 95  in pct else "N/A"),
        ("p99",              ms_label(pct[99])  if 99  in pct else "N/A"),
        ("Max",              ms_label(pct[100]) if 100 in pct else "N/A"),
        ("Transfer Rate",    f"{stats['transfer_kbs']} KB/s" if stats['transfer_kbs'] != "N/A" else "N/A"),
    ]

    for i, (label, value) in enumerate(rows):
        y = 1 - (i + 1) / (len(rows) + 1)
        if label == "Status":
            vc = RED if stats["incomplete"] else GREEN
        elif label == "Failed Requests" and stats["failed_req"] not in (0, "N/A"):
            vc = RED
        else:
            vc = "#111111"
        ax6.text(0.05, y, label, transform=ax6.transAxes,
                 color="#555555", fontsize=10, va="center")
        ax6.text(0.6,  y, value, transform=ax6.transAxes,
                 color=vc, fontsize=10, va="center", fontweight="bold")
        ax6.plot([0.02, 0.98],
                 [y - 0.5/(len(rows)+1), y - 0.5/(len(rows)+1)],
                 color=GRID, linewidth=0.5, transform=ax6.transAxes)

    # â”€â”€ Footer â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    total = stats["total_req"] or 0
    fail  = stats["failed_req"] if stats["failed_req"] != "N/A" else 0
    fail_rate = (fail / total * 100) if total else 0
    note  = "Run was cut off â€” only partial data available" if stats["incomplete"] else ""
    fig.text(0.5, 0.005,
             f"Failure rate: {fail_rate:.2f}%  |  Source: {os.path.basename(txt_path)}"
             + (f"  |  {note}" if note else ""),
             ha="center", color=RED if stats["incomplete"] else "#777777", fontsize=8)

    fig.savefig(out_path, dpi=150, bbox_inches="tight", facecolor="white")
    print(f"âœ“ Saved â†’ {out_path}")
    return out_path

# â”€â”€ Entry point â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

if __name__ == "__main__":
    args = sys.argv[1:]

    if len(args) == 3:
        csv_f, dat_f, txt_f = args
    elif len(args) == 1 and args[0].endswith(".txt"):
        # txt only mode
        csv_f, dat_f, txt_f = None, None, args[0]
    elif len(args) == 0:
        csv_f, dat_f, txt_f = find_files()
    else:
        print("Usage:")
        print("  python3 ab_analyze.py a.csv a.dat a.txt")
        print("  python3 ab_analyze.py a.txt          # txt only")
        print("  python3 ab_analyze.py                # auto-detect")
        sys.exit(1)

    base = os.path.splitext(os.path.basename(txt_f))[0]
    out  = f"{base}_graph.png"
    plot(csv_f, dat_f, txt_f, out)
