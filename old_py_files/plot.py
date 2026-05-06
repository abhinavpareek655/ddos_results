"""
plot_3d.py
----------
Generates a single high-quality 3D EPS figure from 5 pairs of Apache Bench
.dat files and server-resource .csv files.

Design
------
Each scenario occupies its own horizontal "shelf" separated by a fixed Z
offset (SHELF_GAP). Within each shelf:

  • Orange filled ribbon  = avg_load_pct (CSV), rising from the shelf floor
  • Blue vertical stems   = individual ttime values (DAT), plotted at each
                            request's actual relative-time position.  Every
                            stem is a crisp vertical line so spikes never
                            merge into a surface.

Axes
----
X  – Relative time within each test run (0–100 %)
Y  – Scenario (c50 → c100 → c500 → c1000 → spoofing), evenly spaced
Z  – Combined axis:
       lower part of each band  → avg_load_pct  (0–100, orange)
       upper part of each band  → ttime (ms, blue, log-scaled for visibility)

Usage
-----
  python plot_3d.py

Put the script in the same folder as the 10 data files, or edit FILE_PAIRS.
Output: output_3d.eps  +  output_3d.png (preview)
"""

import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D          # noqa: F401
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from matplotlib.patches import Patch
from matplotlib.lines   import Line2D
from scipy.interpolate  import interp1d

# ── USER CONFIGURATION ──────────────────────────────────────────────────────

SCRIPT_DIR = "E:/data3/"

FILE_PAIRS = [
    ("c50",      os.path.join(SCRIPT_DIR, "c50.dat"),      os.path.join(SCRIPT_DIR, "c50.csv")),
    ("c100",     os.path.join(SCRIPT_DIR, "c100.dat"),     os.path.join(SCRIPT_DIR, "c100.csv")),
    ("c500",     os.path.join(SCRIPT_DIR, "c500.dat"),     os.path.join(SCRIPT_DIR, "c500.csv")),
    ("c1000",    os.path.join(SCRIPT_DIR, "c1000.dat"),    os.path.join(SCRIPT_DIR, "c1000.csv")),
    ("spoofing", os.path.join(SCRIPT_DIR, "spoofing.dat"), os.path.join(SCRIPT_DIR, "spoofing.csv")),
]

OUTPUT_EPS = os.path.join(SCRIPT_DIR, "output_3d.eps")
OUTPUT_PNG = os.path.join(SCRIPT_DIR, "output_3d.png")

# ── LAYOUT CONSTANTS ────────────────────────────────────────────────────────

N_INTERP    = 300          # interpolation resolution for avg_load ribbon
LOAD_HEIGHT = 160          # max Z height of the avg_load band per shelf (= 100 %)
TTIME_HEIGHT= 180          # max Z height allocated to ttime spikes above the shelf
SHELF_GAP   = 390          # total Z space per shelf (LOAD_HEIGHT + TTIME_HEIGHT + padding)
Y_SPACING   = 2.2          # spacing between shelves along Y axis

# Colours
C_LOAD  = "#E8761A"        # orange  – avg load surface
C_TTIME = "#2196F3"        # blue    – ttime spikes
C_FLOOR = "#D0D0D0"        # light grey – shelf floor grid line

# ── FONTS ───────────────────────────────────────────────────────────────────

matplotlib.rcParams.update({
    "font.family":    "serif",
    "font.serif":     ["Times New Roman", "Times", "DejaVu Serif", "serif"],
    "font.size":      24,
    "axes.labelsize": 24,
    "xtick.labelsize":18,
    "ytick.labelsize":20,
    "axes.linewidth": 1.2,
})

# ── HELPERS ─────────────────────────────────────────────────────────────────

def load_dat(path):
    df = pd.read_csv(path, sep="\t")
    df.columns = df.columns.str.strip()
    df["ts"] = pd.to_datetime(df["starttime"], format="%a %b %d %H:%M:%S %Y")
    df = df.sort_values("ts").reset_index(drop=True)
    t0 = df["ts"].iloc[0]; t1 = df["ts"].iloc[-1]
    span = (t1 - t0).total_seconds()
    df["rel"] = 0.0 if span == 0 else (df["ts"] - t0).dt.total_seconds() / span
    return df


def load_csv(path):
    df = pd.read_csv(path)
    df.columns = df.columns.str.strip()
    df["ts"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values("ts").reset_index(drop=True)
    t0 = df["ts"].iloc[0]; t1 = df["ts"].iloc[-1]
    span = (t1 - t0).total_seconds()
    df["rel"] = 0.0 if span == 0 else (df["ts"] - t0).dt.total_seconds() / span
    return df


def interp_load(rel, vals, n=N_INTERP):
    s = pd.Series(rel)
    mask = ~s.duplicated(keep="last").values
    rt = np.array(rel)[mask]; v = np.array(vals)[mask]
    idx = np.argsort(rt); rt, v = rt[idx], v[idx]
    xg = np.linspace(0, 1, n)
    if len(rt) < 2:
        return xg, np.full(n, float(v.mean()) if len(v) else 0)
    f = interp1d(rt, v, kind="linear", bounds_error=False,
                 fill_value=(v[0], v[-1]))
    return xg, f(xg)

# ── MAIN ────────────────────────────────────────────────────────────────────

def main():
    n = len(FILE_PAIRS)

    # ── 1. Load and normalise all data ───────────────────────────────────────
    datasets = []
    global_ttime_max = 1.0

    for label, dpath, cpath in FILE_PAIRS:
        dat = load_dat(dpath)
        csv = load_csv(cpath)
        xg, load_interp = interp_load(csv["rel"].values, csv["avg_load_pct"].values)
        # Normalise load to 0-1 then scale to LOAD_HEIGHT
        # Normalise per-scenario: stretch min→max to fill LOAD_HEIGHT
        # so the shape/variation is clearly visible even when absolute
        # range is narrow (e.g. 26–100 %).
        l_min = load_interp.min(); l_max = load_interp.max()
        span_l = l_max - l_min if l_max > l_min else 1.0
        load_norm = (load_interp - l_min) / span_l * LOAD_HEIGHT
        # store per-scenario range for Z axis labels
        ds_load_range = (l_min, l_max)
        # ttime: keep raw ms values, not interpolated – plot each request individually
        ttime_raw = dat["ttime"].values.astype(float)
        ttime_rel = dat["rel"].values
        global_ttime_max = max(global_ttime_max, ttime_raw.max())
        datasets.append(dict(
            label=label,
            xg=xg,
            load=load_norm,
            load_range=(l_min, l_max),
            ttime_rel=ttime_rel,
            ttime_ms=ttime_raw,
        ))

    # ── 2. Figure setup ──────────────────────────────────────────────────────
    fig = plt.figure(figsize=(22, 13))
    ax  = fig.add_subplot(111, projection="3d")

    y_positions = np.arange(n) * Y_SPACING   # [0, 1.8, 3.6, 5.4, 7.2]

    # ── 3. Draw each scenario ────────────────────────────────────────────────
    for i, (ds, yc) in enumerate(zip(datasets, y_positions)):
        z_floor = i * SHELF_GAP              # absolute Z floor for this shelf

        xg   = ds["xg"]
        load = ds["load"]                    # 0 – LOAD_HEIGHT

        # — 3a. Avg load filled ribbon (orange) ——————————————————————————————
        # polygon: outline of load curve + return along floor
        px = np.concatenate([xg, xg[::-1]])
        pz = np.concatenate([z_floor + load, np.full(N_INTERP, z_floor)])
        py = np.full_like(px, yc)

        poly = Poly3DCollection(
            [list(zip(px, py, pz))],
            alpha=0.70,
            facecolor=C_LOAD,
            edgecolor="none",
            zorder=i
        )
        ax.add_collection3d(poly)

        # top edge outline
        ax.plot(xg, np.full(N_INTERP, yc), z_floor + load,
                color=C_LOAD, linewidth=2.0, alpha=1.0, zorder=i+1)

        # floor baseline
        ax.plot([0, 1], [yc, yc], [z_floor, z_floor],
                color=C_FLOOR, linewidth=0.8, linestyle="-", alpha=0.6)

        # — 3b. ttime stems (blue) ————————————————————————————————————————————
        # Each request = one vertical line from the load surface up to ttime height
        # ttime is log-scaled so huge outlier spikes don't crush normal values
        trel = ds["ttime_rel"]
        tms  = ds["ttime_ms"]

        # log scale: map ttime to TTIME_HEIGHT band above LOAD_HEIGHT
        log_t   = np.log1p(tms)                          # log(1+ms)
        log_max = np.log1p(global_ttime_max)
        t_norm  = log_t / log_max * TTIME_HEIGHT         # 0 – TTIME_HEIGHT

        # Z base for ttime = z_floor + LOAD_HEIGHT (sits on top of load band)
        z_ttime_floor = z_floor + LOAD_HEIGHT

        # For each request, find the load value at the nearest x position
        # so ttime stems grow from the load surface (visually anchored)
        load_at_request = np.interp(trel, xg, load)

        for j in range(len(trel)):
            x_j    = trel[j]
            z_base = z_floor + load_at_request[j]    # stem starts at load surface
            z_top  = z_ttime_floor + t_norm[j]
            ax.plot([x_j, x_j], [yc, yc],
                    [z_base, z_top],
                    color=C_TTIME, linewidth=2.2, alpha=0.90, zorder=i+2)

        # thin connecting line through ttime tops for trend readability
        order   = np.argsort(trel)
        ax.plot(trel[order], np.full(len(trel), yc),
                z_ttime_floor + t_norm[order],
                color=C_TTIME, linewidth=0.9, alpha=0.40, linestyle="-", zorder=i+2)

        # — 3c. Scenario label on the Y axis ——————————————————————————————————
        ax.text(-0.06, yc, z_floor + LOAD_HEIGHT / 2,
                ds["label"],
                fontsize=22, ha="right", va="center",
                color="black", fontweight="bold")

    # ── 4. Axis configuration ────────────────────────────────────────────────

    z_total = (n - 1) * SHELF_GAP + LOAD_HEIGHT + TTIME_HEIGHT + 20

    ax.set_xlim(0, 1)
    ax.set_ylim(-0.5, (n - 1) * Y_SPACING + 0.5)
    ax.set_zlim(0, z_total)

    # X: relative time labels
    ax.set_xticks(np.linspace(0, 1, 6))
    ax.set_xticklabels([f"{int(v*100)}%" for v in np.linspace(0, 1, 6)], fontsize=18)

    # Y: hide default ticks (labels drawn manually above)
    ax.set_yticks([])

    # Z: show 3 ticks for the first shelf's load band, well spaced
    first_lmin, first_lmax = datasets[0]["load_range"]
    z_tick_vals  = [0, LOAD_HEIGHT * 0.5, LOAD_HEIGHT]
    z_tick_lbls  = [f"{first_lmin:.0f}%",
                    f"{(first_lmin+first_lmax)/2:.0f}%",
                    f"{first_lmax:.0f}%"]
    ax.set_zticks(z_tick_vals)
    ax.set_zticklabels(z_tick_lbls, fontsize=18)

    ax.set_xlabel("Relative Time within Test Run", fontsize=24, labelpad=16)
    ax.set_ylabel("", fontsize=1)    # blank – labels are drawn as 3D text
    ax.set_zlabel("Avg Load  (% per shelf)", fontsize=22, labelpad=14)

    # ── 5. Annotations: ttime scale reference ────────────────────────────────
    # Show what the tallest blue spike corresponds to in ms
    fig.text(0.91, 0.80,
             f"ttime (log scale)\n"
             f"top spike ≈ {int(global_ttime_max):,} ms\n"
             f"({int(global_ttime_max/1000):.0f} s)",
             fontsize=16, color=C_TTIME, ha="center", va="top",
             bbox=dict(boxstyle="round,pad=0.4", facecolor="white",
                       edgecolor=C_TTIME, linewidth=1.5, alpha=0.9))

    # ── 6. Legend ────────────────────────────────────────────────────────────
    legend_elements = [
        Patch(facecolor=C_LOAD,  alpha=0.75, label="Avg Server Load (%)"),
        Line2D([0], [0], color=C_TTIME, linewidth=2.5,
               label="Request Response Time – ttime (ms, log)"),
    ]
    ax.legend(handles=legend_elements,
              loc="upper left", fontsize=20, framealpha=0.90,
              edgecolor="#cccccc")

    # ── 7. View angle ────────────────────────────────────────────────────────
    ax.view_init(elev=18, azim=-55)

    # ── 8. Pane and grid styling ─────────────────────────────────────────────
    for pane in (ax.xaxis.pane, ax.yaxis.pane, ax.zaxis.pane):
        pane.fill = False
        pane.set_edgecolor("#aaaaaa")
    ax.grid(True, linestyle="--", linewidth=0.4, alpha=0.35)

    fig.subplots_adjust(left=0.05, right=0.88, top=0.97, bottom=0.03)

    # ── 9. Save ──────────────────────────────────────────────────────────────
    fig.savefig(OUTPUT_EPS, format="eps", dpi=300, bbox_inches="tight")
    fig.savefig(OUTPUT_PNG, format="png", dpi=200, bbox_inches="tight")
    print(f"Saved EPS : {OUTPUT_EPS}")
    print(f"Saved PNG : {OUTPUT_PNG}")
    plt.close(fig)


if __name__ == "__main__":
    main()