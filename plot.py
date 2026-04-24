import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from matplotlib.patches import Patch
from matplotlib.lines import Line2D
from matplotlib import cm, colors as mcolors
from scipy.interpolate import interp1d

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

FILE_PAIRS = [
    ("c50",      os.path.join(SCRIPT_DIR, "c50.dat"),      os.path.join(SCRIPT_DIR, "c50.csv")),
    ("c100",     os.path.join(SCRIPT_DIR, "c100.dat"),     os.path.join(SCRIPT_DIR, "c100.csv")),
    ("c500",     os.path.join(SCRIPT_DIR, "c500.dat"),     os.path.join(SCRIPT_DIR, "c500.csv")),
    ("c1000",    os.path.join(SCRIPT_DIR, "c1000.dat"),    os.path.join(SCRIPT_DIR, "c1000.csv")),
    ("spoofing", os.path.join(SCRIPT_DIR, "spoofing.dat"), os.path.join(SCRIPT_DIR, "spoofing.csv")),
]

OUTPUT_EPS = os.path.join(SCRIPT_DIR, "output_3d.eps")
OUTPUT_PNG = os.path.join(SCRIPT_DIR, "output_3d.png")

# ── LAYOUT ───────────────────────────────────────────────────────────────────
N_X          = 60          # X resolution of the surface mesh
N_Y_PER_SCN  = 3           # Y slices per scenario (controls Y mesh density)
Y_SPACING    = 2.0         # Y distance between scenario centres
FONT_SIZE    = 36

# Z axis: load occupies 0–100 (actual percent), no artificial scaling
Z_MAX_LOAD   = 100.0       # Z = avg_load_pct directly (0–100)

# Colours
C_TTIME      = "#2196F3"
C_WALL       = "#F5F5F5"
C_GRID       = "#545454"

TTIME_MARKER_SIZE = 40
TTIME_MARKER_LW   = 2.0
N_TTIME_TICKS     = 5

matplotlib.rcParams.update({
    "font.family":     "serif",
    "font.serif":      ["Times New Roman", "Times", "DejaVu Serif", "serif"],
    "font.size":       FONT_SIZE,
    "axes.labelsize":  FONT_SIZE,
    "xtick.labelsize": FONT_SIZE - 4,
    "ytick.labelsize": FONT_SIZE - 2,
    "axes.linewidth":  1.2,
})

# ── HELPERS ──────────────────────────────────────────────────────────────────

def load_dat(path):
    df = pd.read_csv(path, sep="\t")
    df.columns = df.columns.str.strip()
    df["ts"] = pd.to_datetime(df["starttime"], format="%a %b %d %H:%M:%S %Y")
    df = df.sort_values("ts").reset_index(drop=True)
    t0 = df["ts"].iloc[0]; t1 = df["ts"].iloc[-1]
    span = (t1 - t0).total_seconds()
    df["rel"] = 0.0 if span == 0 else (df["ts"] - t0).dt.total_seconds() / span
    return df, t0, t1


def load_csv(path, t0, t1):
    df = pd.read_csv(path)
    df.columns = df.columns.str.strip()
    df["ts"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values("ts").reset_index(drop=True)
    span = (t1 - t0).total_seconds()
    df["rel"] = 0.0 if span == 0 else (df["ts"] - t0).dt.total_seconds() / span
    return df


def interp_load(rel, vals, n=N_X):
    """Interpolate load onto a uniform x grid; return values in raw %."""
    s = pd.Series(rel)
    mask = ~s.duplicated(keep="last").values
    rt = np.array(rel)[mask]; v = np.array(vals)[mask]
    idx = np.argsort(rt); rt, v = rt[idx], v[idx]
    xg = np.linspace(0, 1, n)
    if len(rt) < 2:
        return xg, np.full(n, float(v.mean()) if len(v) else 0)
    f = interp1d(rt, v, kind="linear", bounds_error=False,
                 fill_value=(v[0], v[-1]))
    return xg, np.clip(f(xg), 0.0, 100.0)


def ttime_tick_values(max_ms, n_ticks=N_TTIME_TICKS):
    top = max(float(max_ms), 1.0)
    vals = np.geomspace(1.0, top, n_ticks)
    vals = np.unique(np.round(vals).astype(int))
    if vals[-1] != int(round(top)):
        vals = np.append(vals, int(round(top)))
    return vals


def make_surface_arrays(datasets, y_positions, n_x=N_X, n_y_per=N_Y_PER_SCN):
    """
    Build unified X, Y, Z numpy 2-D arrays for ax.plot_surface.

    X : relative time (0–1), same for every row
    Y : scenario position – each scenario occupies n_y_per rows that all
        share the same y_position so the surface is flat across Y within
        a scenario and the transitions between scenarios show connectivity
    Z : avg_load_pct (0–100), directly – so Z axis labels map 1-to-1
    """
    n_scn   = len(datasets)
    # One extra duplicate row per boundary so the surface visually 'touches'
    # each neighbouring scenario at a shared Y edge
    total_y = n_scn * n_y_per

    X_arr = np.zeros((total_y, n_x))
    Y_arr = np.zeros((total_y, n_x))
    Z_arr = np.zeros((total_y, n_x))

    xg = np.linspace(0, 1, n_x)

    for i, (ds, yc) in enumerate(zip(datasets, y_positions)):
        load_row = ds["load_pct"]   # shape (n_x,) in percent

        row_start = i * n_y_per
        for r in range(n_y_per):
            row = row_start + r
            X_arr[row, :] = xg
            Y_arr[row, :] = yc
            Z_arr[row, :] = load_row

    return X_arr, Y_arr, Z_arr


def main():
    n = len(FILE_PAIRS)
    datasets        = []
    global_ttime_max = 1.0

    for label, dpath, cpath in FILE_PAIRS:
        dat, t0, t1  = load_dat(dpath)
        csv          = load_csv(cpath, t0, t1)
        xg, load_pct = interp_load(csv["rel"].values, csv["avg_load_pct"].values)
        ttime_raw    = dat["ttime"].values.astype(float)
        ttime_rel    = dat["rel"].values
        global_ttime_max = max(global_ttime_max, ttime_raw.max())
        datasets.append(dict(
            label    = label,
            xg       = xg,
            load_pct = load_pct,          # raw %, 0–100
            ttime_rel= ttime_rel,
            ttime_ms = ttime_raw,
        ))

    # ── Y positions for each scenario ────────────────────────────────────────
    y_positions = np.arange(n, dtype=float) * Y_SPACING   # 0, 2, 4, 6, 8

    # ── Build the unified surface ─────────────────────────────────────────────
    X, Y, Z = make_surface_arrays(datasets, y_positions)

    # ── Colour-map: red gradient mapped to load height ────────────────────────
    # Use a red colormap (Reds) so low load = pale pink, high = deep red
    cmap_load = cm.get_cmap("Reds")
    norm_load  = mcolors.Normalize(vmin=0, vmax=100)
    face_colors = cmap_load(norm_load(Z))          # RGBA array

    # ── Figure & axes ─────────────────────────────────────────────────────────
    fig = plt.figure(figsize=(40, 20))
    ax  = fig.add_subplot(111, projection="3d")

    # ── Draw the continuous surface ───────────────────────────────────────────
    surf = ax.plot_surface(
        X, Y, Z,
        facecolors  = face_colors,
        edgecolor   = "#FFFFFF",       # dark red mesh lines
        linewidth   = 0.45,
        shade       = True,
        alpha       = 0.90,
        antialiased = True,
        zorder      = 5,
    )

    # ── Draw ttime stems + markers per scenario ───────────────────────────────
    log_max = np.log1p(global_ttime_max)
    # ttime is drawn above Z_MAX_LOAD; scale it to a fixed extra band
    TTIME_BAND = 40.0    # percent-equivalent units above 100%

    for i, (ds, yc) in enumerate(zip(datasets, y_positions)):
        trel  = ds["ttime_rel"]
        tms   = ds["ttime_ms"]
        t_norm = np.log1p(tms) / log_max * TTIME_BAND   # 0 – TTIME_BAND

        z_tips = Z_MAX_LOAD + t_norm

        # for j in range(len(trel)):
        #     ax.plot([trel[j], trel[j]], [yc, yc],
        #             [0, z_tips[j]],
        #             color=C_TTIME, linewidth=1.6, alpha=0.80, zorder=10)

        ax.scatter(
            trel, np.full(len(trel), yc), z_tips,
            marker="x", s=TTIME_MARKER_SIZE, linewidths=TTIME_MARKER_LW,
            color=C_TTIME, alpha=0.95, depthshade=False, zorder=11,
        )

        # Trend line through ttime tips
        order = np.argsort(trel)
        ax.plot(trel[order], np.full(len(trel), yc), z_tips[order],
                color=C_TTIME, linewidth=3.2, alpha=0.65, linestyle="-", zorder=10)

    # ── Axis limits ───────────────────────────────────────────────────────────
    z_top = Z_MAX_LOAD + TTIME_BAND + 2
    ax.set_xlim(0, 1)
    ax.set_ylim(y_positions[0] - 0.5, y_positions[-1] + 0.5)
    ax.set_zlim(0, z_top)

    # ── X ticks: relative time ────────────────────────────────────────────────
    x_tick_vals = np.linspace(0, 1, 11)
    ax.set_xticks(x_tick_vals)
    ax.set_xticklabels([f"{int(v*100)}%" for v in x_tick_vals],
                       fontsize=FONT_SIZE - 4)

    # ── Y ticks: scenario names exactly at their Y positions ──────────────────
    ax.set_yticks(y_positions)
    ax.set_yticklabels([ds["label"] for ds in datasets],
                       fontsize=FONT_SIZE - 2)

    # ── Z ticks: load % (0–100) aligned with gridlines ───────────────────────
    # These are in the same units as Z, so gridlines land exactly on tick marks
    load_tick_pcts  = [0, 25, 50, 75, 100]
    load_z_ticks    = [float(v) for v in load_tick_pcts]
    load_z_labels   = [f"{v}%" for v in load_tick_pcts]

    # ttime ticks sit above 100%
    ttime_ticks_ms  = ttime_tick_values(global_ttime_max)
    ttime_z_ticks   = [Z_MAX_LOAD + (np.log1p(ms) / log_max) * TTIME_BAND
                       for ms in ttime_ticks_ms]
    ttime_z_labels  = [f"{int(ms):,} ms" for ms in ttime_ticks_ms]

    all_z_ticks  = load_z_ticks  + ttime_z_ticks
    all_z_labels = load_z_labels + ttime_z_labels

    ax.set_zticks(all_z_ticks)
    ax.set_zticklabels(all_z_labels, fontsize=FONT_SIZE - 5)

    # ── Axis labels ───────────────────────────────────────────────────────────
    ax.set_xlabel("Relative Time within Test Run",
                  fontsize=FONT_SIZE, labelpad=38)
    ax.set_ylabel("Scenario", fontsize=FONT_SIZE, labelpad=38)
    ax.set_zlabel("Avg Load (%)  /  ttime (ms, log)",
                  fontsize=FONT_SIZE, labelpad=38)

    # ── Wall panes: light fill so gridlines are clearly visible ───────────────
    for pane in (ax.xaxis.pane, ax.yaxis.pane, ax.zaxis.pane):
        pane.fill = True
        pane.set_facecolor(C_WALL)
        pane.set_edgecolor("#BFBFBF")

    # Dense solid gridlines – these now align with load % tick values
    ax.grid(True, linestyle="-", linewidth=0.7, color=C_GRID, alpha=0.75)

    # ── Colourbar for avg load ────────────────────────────────────────────────
    # sm = cm.ScalarMappable(cmap=cmap_load, norm=norm_load)
    # sm.set_array([])
    # cbar = fig.colorbar(sm, ax=ax, shrink=0.45, pad=0.04, aspect=18)
    # cbar.set_label("Avg Load (%)", fontsize=FONT_SIZE - 4)
    # cbar.ax.tick_params(labelsize=FONT_SIZE - 6)

    # ── Legend ────────────────────────────────────────────────────────────────
    # legend_elements = [
    #     Patch(facecolor=cmap_load(0.85), alpha=0.90, label="Avg Server Load (%)"),
    #     Line2D([0], [0], color=C_TTIME, linewidth=2.0, label="ttime (ms, log-scale)"),
    #     Line2D([0], [0], linestyle="None", marker="x", markersize=9,
    #            markeredgewidth=2, color=C_TTIME, label="ttime datapoints"),
    # ]
    # ax.legend(handles=legend_elements,
    #           loc="upper left", fontsize=FONT_SIZE - 4,
    #           framealpha=0.92, edgecolor="#cccccc")

    # ── View angle ────────────────────────────────────────────────────────────
    ax.view_init(elev=25, azim=-50)

    # Leave extra room on the right for long 3D z tick labels (ms values).
    fig.subplots_adjust(left=0.04, right=0.84, top=0.97, bottom=0.04)

    # ── Save ──────────────────────────────────────────────────────────────────
    fig.savefig(OUTPUT_EPS, format="eps", dpi=300, bbox_inches="tight", pad_inches=0.50)
    fig.savefig(OUTPUT_PNG, format="png", dpi=200, bbox_inches="tight", pad_inches=0.50)
    print(f"Saved EPS : {OUTPUT_EPS}")
    print(f"Saved PNG : {OUTPUT_PNG}")
    plt.close(fig)


if __name__ == "__main__":
    main()