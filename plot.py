import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D        
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from matplotlib.patches import Patch
from matplotlib.lines   import Line2D
from scipy.interpolate  import interp1d

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

N_INTERP    = 300          # interpolation resolution for avg_load ribbon
LOAD_HEIGHT = 500         # max Z height of the avg_load band per shelf (= 100 %)
TTIME_HEIGHT= 420          # max Z height allocated to ttime spikes above the shelf
SHELF_GAP   = 390          # total Z space per shelf (LOAD_HEIGHT + TTIME_HEIGHT + padding)
Y_SPACING   = 2.0          # spacing between shelves along Y axis
FONT_SIZE   = 36

# Colours
C_LOAD        = "#E8761A"  # orange  – avg load surface
C_TTIME       = "#2196F3"  # blue    – ttime spikes
C_FLOOR       = "#686868"  # light grey – shelf floor grid line
C_LOAD_GRID   = "#686868"  # light grey – load reference boundaries
C_TTIME_GRID  = "#686868"  # light grey – ttime reference boundaries
TTIME_MARKER_SIZE = 48     # size of x markers on top of each ttime stem
TTIME_MARKER_LW   = 2.5   # x marker stroke width
N_TTIME_TICKS     = 5     # reference ticks for ttime scale labels/grid

# ── DIAGONAL GRID SETTINGS ───────────────────────────────────────────────────
# Load % reference levels shown as diagonal planes across all shelves
LOAD_GRID_LEVELS   = [0.25, 0.50, 0.75, 1.00]   # fraction of LOAD_HEIGHT
LOAD_GRID_ALPHA    = 0.0
LOAD_GRID_LW       = 1.4
GRID_MARKER_SIZE   = 16
GRID_MARKER_ALPHA  = 0.95

# ttime reference levels are generated from stretched fractions in log space.
TTIME_GRID_N_LEVELS = 4
TTIME_GRID_MIN_FRAC = 0.15
TTIME_GRID_ALPHA   = 0.0
TTIME_GRID_LW      = 1.4

# ── FONTS ───────────────────────────────────────────────────────────────────

matplotlib.rcParams.update({
    "font.family":    "serif",
    "font.serif":     ["Times New Roman", "Times", "DejaVu Serif", "serif"],
    "font.size":      FONT_SIZE,
    "axes.labelsize": FONT_SIZE,
    "xtick.labelsize": FONT_SIZE,
    "ytick.labelsize": FONT_SIZE,
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
    return df, t0, t1


def load_csv(path, t0, t1):
    df = pd.read_csv(path)
    df.columns = df.columns.str.strip()
    df["ts"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values("ts").reset_index(drop=True)
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


def ttime_tick_values(max_ms, n_ticks=N_TTIME_TICKS):
    """Return log-spaced ttime tick values in milliseconds."""
    top = max(float(max_ms), 1.0)
    vals = np.geomspace(1.0, top, n_ticks)
    vals = np.unique(np.round(vals).astype(int))
    if vals[-1] != int(round(top)):
        vals = np.append(vals, int(round(top)))
    return vals


def stretched_ttime_ms_levels(max_ms, n_levels=TTIME_GRID_N_LEVELS,
                              min_frac=TTIME_GRID_MIN_FRAC):
    """Generate ttime grid levels with wider spacing in plotted Z space."""
    top = max(float(max_ms), 1.0)
    fracs = np.linspace(min_frac, 1.0, n_levels)
    ms_vals = np.expm1(fracs * np.log1p(top))
    ms_vals = np.unique(np.round(ms_vals).astype(int))
    ms_vals = ms_vals[ms_vals > 0]
    if len(ms_vals) == 0:
        return np.array([int(round(top))])
    if ms_vals[-1] != int(round(top)):
        ms_vals = np.append(ms_vals, int(round(top)))
    return ms_vals


def draw_diagonal_load_grid(ax, n, y_positions, load_levels, shelf_gap, load_height):
    """
    Draw diagonal reference planes for avg-load percentage levels.
    Each plane sweeps from shelf 0 (y=y_positions[0]) to shelf n-1
    (y=y_positions[-1]), rising in Z by one SHELF_GAP per step so it
    stays at the same *relative* height on every shelf – giving the
    staircase/diagonal look seen in the reference image.

        For each level we draw boundary segments for every shelf intersection
        so all iteration lines are visible.
    """
    for frac in load_levels:
        z_rel = frac * load_height     # Z offset *within* each shelf

        # Build the diagonal ribbon: one quad per shelf-to-shelf step
        # so the plane follows the staircase exactly.
        # Vertices: bottom-left, bottom-right of current shelf →
        #           top-right, top-left of next shelf.
        # We collect all quads as a single Poly3DCollection.
        verts = []
        for i in range(n):
            z_i = i * shelf_gap + z_rel
            y_i = y_positions[i]

            if i < n - 1:
                z_j = (i + 1) * shelf_gap + z_rel
                y_j = y_positions[i + 1]

                # Quad connecting shelf i to shelf i+1 at this load level
                quad = [
                    (0.0, y_i, z_i),
                    (1.0, y_i, z_i),
                    (1.0, y_j, z_j),
                    (0.0, y_j, z_j),
                ]
                verts.append(quad)

        poly = Poly3DCollection(
            verts,
            alpha=LOAD_GRID_ALPHA,
            facecolor=(0, 0, 0, 0),
            edgecolor=C_LOAD_GRID,
            linewidth=LOAD_GRID_LW,
        )
        ax.add_collection3d(poly)

        # Explicit boundaries to ensure all plane edges are visible.
        for i in range(n):
            z_i = i * shelf_gap + z_rel
            y_i = y_positions[i]
            ax.plot([0.0, 1.0], [y_i, y_i], [z_i, z_i],
                    color=C_LOAD_GRID, linewidth=LOAD_GRID_LW, alpha=0.95, zorder=6)

            if i < n - 1:
                z_j = (i + 1) * shelf_gap + z_rel
                y_j = y_positions[i + 1]
                ax.plot([0.0, 0.0], [y_i, y_j], [z_i, z_j],
                        color=C_LOAD_GRID, linewidth=LOAD_GRID_LW, alpha=0.95, zorder=6)
                ax.plot([1.0, 1.0], [y_i, y_j], [z_i, z_j],
                        color=C_LOAD_GRID, linewidth=LOAD_GRID_LW, alpha=0.95, zorder=6)

        # Bold top edge along the final (back) shelf for label anchoring
        z_back = (n - 1) * shelf_gap + z_rel
        y_back = y_positions[-1]
        ax.plot([0.0, 1.0], [y_back, y_back], [z_back, z_back],
                color=C_LOAD_GRID, linewidth=LOAD_GRID_LW, alpha=0.95, zorder=7)

        # Also draw the front edge on shelf 0 for readability
        z_front = z_rel
        y_front = y_positions[0]
        ax.plot([0.0, 1.0], [y_front, y_front], [z_front, z_front],
                color=C_LOAD_GRID, linewidth=LOAD_GRID_LW, alpha=0.95,
                linestyle="--", zorder=7)

        # Mark where this reference level meets each scenario shelf.
        z_pts = np.array([k * shelf_gap + z_rel for k in range(n)])
        y_pts = np.array(y_positions)
        ax.scatter(np.full(n, 1.0), y_pts, z_pts,
               s=GRID_MARKER_SIZE, color=C_LOAD_GRID, alpha=GRID_MARKER_ALPHA,
               depthshade=False, zorder=8)

        # Label at top-right corner of the back shelf
        ax.text(1.02, y_back, z_back,
                f"{int(frac*100)}%",
            fontsize=FONT_SIZE, ha="left", va="center",
                color=C_LOAD_GRID, fontweight="bold")


def draw_diagonal_ttime_grid(ax, n, y_positions, ttime_ms_levels,
                             shelf_gap, load_height, ttime_height,
                             global_ttime_max):
    """
    Draw diagonal reference planes for ttime millisecond levels (blue).
    Same staircase logic as load grid but the Z offset is the ttime
    log-scaled value sitting on top of LOAD_HEIGHT.
    """
    log_max = np.log1p(global_ttime_max)

    for ms in ttime_ms_levels:
        if ms > global_ttime_max:
            continue   # skip levels beyond actual data range

        # Z offset within the ttime band (above LOAD_HEIGHT)
        z_ttime_offset = load_height + (np.log1p(ms) / log_max) * ttime_height

        verts = []
        for i in range(n):
            z_i = i * shelf_gap + z_ttime_offset
            y_i = y_positions[i]

            if i < n - 1:
                z_j = (i + 1) * shelf_gap + z_ttime_offset
                y_j = y_positions[i + 1]

                quad = [
                    (0.0, y_i, z_i),
                    (1.0, y_i, z_i),
                    (1.0, y_j, z_j),
                    (0.0, y_j, z_j),
                ]
                verts.append(quad)

        poly = Poly3DCollection(
            verts,
            alpha=TTIME_GRID_ALPHA,
            facecolor=(0, 0, 0, 0),
            edgecolor=C_TTIME_GRID,
            linewidth=TTIME_GRID_LW,
        )
        ax.add_collection3d(poly)

        # Explicit boundaries to ensure all plane edges are visible.
        for i in range(n):
            z_i = i * shelf_gap + z_ttime_offset
            y_i = y_positions[i]
            ax.plot([0.0, 1.0], [y_i, y_i], [z_i, z_i],
                    color=C_TTIME_GRID, linewidth=TTIME_GRID_LW, alpha=0.95, zorder=6)

            if i < n - 1:
                z_j = (i + 1) * shelf_gap + z_ttime_offset
                y_j = y_positions[i + 1]
                ax.plot([0.0, 0.0], [y_i, y_j], [z_i, z_j],
                        color=C_TTIME_GRID, linewidth=TTIME_GRID_LW, alpha=0.95, zorder=6)
                ax.plot([1.0, 1.0], [y_i, y_j], [z_i, z_j],
                        color=C_TTIME_GRID, linewidth=TTIME_GRID_LW, alpha=0.95, zorder=6)

        # Bold edge on back shelf + label
        z_back = (n - 1) * shelf_gap + z_ttime_offset
        y_back = y_positions[-1]
        ax.plot([0.0, 1.0], [y_back, y_back], [z_back, z_back],
                color=C_TTIME_GRID, linewidth=TTIME_GRID_LW, alpha=0.95, zorder=7)

        # Dashed edge on front shelf
        z_front = z_ttime_offset
        y_front = y_positions[0]
        ax.plot([0.0, 1.0], [y_front, y_front], [z_front, z_front],
                color=C_TTIME_GRID, linewidth=TTIME_GRID_LW, alpha=0.95,
                linestyle="--", zorder=7)

        # Mark where this reference level meets each scenario shelf.
        z_pts = np.array([k * shelf_gap + z_ttime_offset for k in range(n)])
        y_pts = np.array(y_positions)
        ax.scatter(np.full(n, 1.0), y_pts, z_pts,
               s=GRID_MARKER_SIZE, color=C_TTIME_GRID, alpha=GRID_MARKER_ALPHA,
               depthshade=False, zorder=8)

        # Label
        label_str = f"{int(ms):,} ms"
        ax.text(1.02, y_back, z_back,
                label_str,
            fontsize=FONT_SIZE, ha="left", va="center", color=C_TTIME_GRID)


def main():
    n = len(FILE_PAIRS)

    datasets = []
    global_ttime_max = 1.0

    for label, dpath, cpath in FILE_PAIRS:
        dat, t0, t1 = load_dat(dpath)
        csv = load_csv(cpath, t0, t1)
        xg, load_interp = interp_load(csv["rel"].values, csv["avg_load_pct"].values)
        l_min = load_interp.min(); l_max = load_interp.max()
        # Preserve true percentage meaning: 100% -> LOAD_HEIGHT.
        load_norm = np.clip(load_interp, 0.0, 100.0) / 100.0 * LOAD_HEIGHT
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
    fig = plt.figure(figsize=(38, 26))
    ax  = fig.add_subplot(111, projection="3d")

    y_positions = np.arange(n) * Y_SPACING

    # ── 3. Draw diagonal grid planes FIRST (behind data) ────────────────────
    draw_diagonal_load_grid(
        ax, n, y_positions,
        LOAD_GRID_LEVELS, SHELF_GAP, LOAD_HEIGHT
    )
    ttime_grid_ms = stretched_ttime_ms_levels(global_ttime_max)
    draw_diagonal_ttime_grid(
        ax, n, y_positions,
        ttime_grid_ms, SHELF_GAP, LOAD_HEIGHT, TTIME_HEIGHT,
        global_ttime_max
    )

    # ── 4. Draw each scenario (on top of grids) ──────────────────────────────
    for i, (ds, yc) in enumerate(zip(datasets, y_positions)):
        z_floor = i * SHELF_GAP

        xg   = ds["xg"]
        load = ds["load"]

        # — 4a. Avg load filled ribbon (orange) ——————————————————————————————
        px = np.concatenate([xg, xg[::-1]])
        pz = np.concatenate([z_floor + load, np.full(N_INTERP, z_floor)])
        py = np.full_like(px, yc)

        poly = Poly3DCollection(
            [list(zip(px, py, pz))],
            alpha=0.70,
            facecolor=C_LOAD,
            edgecolor="none",
            zorder=i + 10
        )
        ax.add_collection3d(poly)

        # top edge outline
        ax.plot(xg, np.full(N_INTERP, yc), z_floor + load,
                color=C_LOAD, linewidth=2.0, alpha=1.0, zorder=i + 11)

        # floor baseline
        ax.plot([0, 1], [yc, yc], [z_floor, z_floor],
                color=C_FLOOR, linewidth=0.8, linestyle="-", alpha=0.2)

        # — 4b. ttime stems (blue) ————————————————————————————————————————————
        trel = ds["ttime_rel"]
        tms  = ds["ttime_ms"]

        log_t   = np.log1p(tms)
        log_max = np.log1p(global_ttime_max)
        t_norm  = log_t / log_max * TTIME_HEIGHT

        z_ttime_floor = z_floor + LOAD_HEIGHT

        for j in range(len(trel)):
            x_j   = trel[j]
            z_base = z_floor
            z_top  = z_ttime_floor + t_norm[j]
            ax.plot([x_j, x_j], [yc, yc],
                    [z_base, z_top],
                    color=C_TTIME, linewidth=2.2, alpha=0.90, zorder=i + 12)

        ax.scatter(
            trel,
            np.full(len(trel), yc),
            z_ttime_floor + t_norm,
            marker="x",
            s=TTIME_MARKER_SIZE,
            linewidths=TTIME_MARKER_LW,
            color=C_TTIME,
            alpha=0.95,
            depthshade=False,
            zorder=i + 13,
        )

        # thin connecting line through ttime tops
        order = np.argsort(trel)
        ax.plot(trel[order], np.full(len(trel), yc),
                z_ttime_floor + t_norm[order],
                color=C_TTIME, linewidth=0.9, alpha=0.40, linestyle="-",
                zorder=i + 12)

        # — 4c. Scenario label ————————————————————————————————————————————————
        ax.text(-0.06, yc, z_floor + LOAD_HEIGHT / 2,
                ds["label"],
            fontsize=FONT_SIZE, ha="right", va="center",
                color="black", fontweight="bold")

    # ── 5. Axis configuration ────────────────────────────────────────────────

    z_total = (n - 1) * SHELF_GAP + LOAD_HEIGHT + TTIME_HEIGHT + 20

    ax.set_xlim(0, 1)
    ax.set_ylim(-0.5, (n - 1) * Y_SPACING + 0.5)
    ax.set_zlim(0, z_total)

    ax.set_xticks(np.linspace(0, 1, 6))
    ax.set_xticklabels([f"{int(v*100)}%" for v in np.linspace(0, 1, 6)], fontsize=FONT_SIZE)
    ax.set_yticks([])

    z_load_vals = [0, LOAD_HEIGHT * 0.5, LOAD_HEIGHT]
    z_load_lbls = ["0%", "50%", "100%"]

    ax.set_zticks(z_load_vals)
    ax.set_zticklabels(z_load_lbls, fontsize=FONT_SIZE)

    ax.set_xlabel("Relative Time within Test Run", fontsize=FONT_SIZE, labelpad=16)
    ax.set_ylabel("", fontsize=FONT_SIZE)
    ax.set_zlabel("Avg Load (% per shelf)", fontsize=FONT_SIZE, labelpad=14)

    # Mirror avg-load labels
    y_side = (n - 1) * Y_SPACING + 0.35
    for z_v, lbl in zip(z_load_vals, z_load_lbls):
        ax.text(-0.08, y_side, z_v, lbl,
            fontsize=FONT_SIZE, ha="right", va="center", color=C_LOAD_GRID)
    ax.text(-0.09, y_side, LOAD_HEIGHT * 0.5,
            "avg load %",
            fontsize=FONT_SIZE, ha="right", va="center", color=C_LOAD_GRID)

    # ttime annotation box
    fig.text(0.91, 0.80,
             f"ttime (log scale)\n"
             f"top spike ≈ {int(global_ttime_max):,} ms\n"
             f"({int(global_ttime_max/1000):.0f} s)",
             fontsize=FONT_SIZE, color=C_TTIME, ha="center", va="top",
             bbox=dict(boxstyle="round,pad=0.4", facecolor="white",
                       edgecolor=C_TTIME, linewidth=1.5, alpha=0.9))

    # ── 6. Legend ────────────────────────────────────────────────────────────
    legend_elements = [
        Patch(facecolor=C_LOAD,  alpha=0.75, label="Avg Server Load (%)"),
        Line2D([0], [0], color=C_TTIME, linewidth=2.5,
               label="ttime stems (ms, log)"),
        Line2D([0], [0], linestyle="None", marker="x", markersize=10,
               markeredgewidth=2, color=C_TTIME,
               label="ttime datapoints"),
         Line2D([0], [0], color=C_LOAD_GRID, linewidth=1.5,
             label="Load % reference boundaries"),
         Line2D([0], [0], color=C_TTIME_GRID, linewidth=1.5,
             label="ttime reference boundaries"),
    ]
    ax.legend(handles=legend_elements,
              loc="upper left", fontsize=FONT_SIZE, framealpha=0.90,
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