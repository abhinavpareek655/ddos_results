import os
import sys
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
BENIGN_DIR = os.path.join(SCRIPT_DIR, "benign/data")
SERVER_DIR = os.path.join(SCRIPT_DIR, "server/data")
EXPERIMENT = sys.argv[1] if len(sys.argv) > 1 else "ac+filtering"

FILE_PAIRS = [
    ("c50",      os.path.join(BENIGN_DIR, EXPERIMENT, "c50/a.dat"),      os.path.join(SERVER_DIR, EXPERIMENT, "c50/haproxy-metrics.csv")),
    ("c100",     os.path.join(BENIGN_DIR, EXPERIMENT, "c100/a.dat"),     os.path.join(SERVER_DIR, EXPERIMENT, "c100/haproxy-metrics.csv")),
    ("c500",     os.path.join(BENIGN_DIR, EXPERIMENT, "c500/a.dat"),     os.path.join(SERVER_DIR, EXPERIMENT, "c500/haproxy-metrics.csv")),
    ("c1000",    os.path.join(BENIGN_DIR, EXPERIMENT, "c1000/a.dat"),    os.path.join(SERVER_DIR, EXPERIMENT, "c1000/haproxy-metrics.csv")),
    ("spoofing", os.path.join(BENIGN_DIR, EXPERIMENT, "spoofing/a.dat"), os.path.join(SERVER_DIR, EXPERIMENT, "spoofing/haproxy-metrics.csv")),
]

OUTPUT_EPS = os.path.join(SCRIPT_DIR, f"{EXPERIMENT}.eps")
OUTPUT_PNG = os.path.join(SCRIPT_DIR, f"{EXPERIMENT}.png")

# ── LAYOUT ───────────────────────────────────────────────────────────────────
N_X          = 60
N_Y_PER_SCN  = 3
Y_SPACING    = 2.0
FONT_SIZE    = 36

Z_MAX_LOAD   = 100.0
TTIME_BAND   = 80.0
TTIME_OFFSET = 15.0

# Colours
C_TTIME      = "#2196F3"
C_WALL       = "#F5F5F5"
C_GRID       = "#545454"
C_SERVER2    = "#2ECC71"   # green  – server 2 up indicator
C_SERVER3    = "#9B59B6"   # purple – server 3 up indicator

TTIME_MARKER_SIZE = 40
TTIME_MARKER_LW   = 2.0
N_TTIME_TICKS     = 5
TTIME_Y_NUDGE     = 0.08

# Server-up backdrop visual settings
SERVER_UP_ALPHA = 0.05   # fill transparency of backdrop wall

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

    # avg_load_pct is written as "" by the autoscaler when no backend servers
    # are reachable. pd.read_csv parses those as NaN.
    # Fix: linearly interpolate each gap using its nearest prev + next values.
    # method="index" weights by the actual row-index distance between neighbours
    # (proportional to time since rows are time-sorted), so a gap of 3 rows gets
    # values at 1/4, 2/4, 3/4 of the way between the surrounding valid readings.
    # limit_direction="both" also handles leading/trailing NaNs at the edges
    # (back-fills a leading gap, forward-fills a trailing gap).
    if "avg_load_pct" in df.columns:
        df["avg_load_pct"] = (
            pd.to_numeric(df["avg_load_pct"], errors="coerce")    # "" → NaN
              .interpolate(method="index", limit_direction="both") # fill gaps
              .clip(0.0, 100.0)                                    # stay in range
        )
    return df


def interp_load(rel, vals, n=N_X):
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
    n_scn   = len(datasets)
    total_y = n_scn * n_y_per
    X_arr = np.zeros((total_y, n_x))
    Y_arr = np.zeros((total_y, n_x))
    Z_arr = np.zeros((total_y, n_x))
    xg = np.linspace(0, 1, n_x)
    for i, (ds, yc) in enumerate(zip(datasets, y_positions)):
        load_row  = ds["load_pct"]
        row_start = i * n_y_per
        for r in range(n_y_per):
            row = row_start + r
            X_arr[row, :] = xg
            Y_arr[row, :] = yc
            Z_arr[row, :] = load_row
    return X_arr, Y_arr, Z_arr


def get_server_up_spans(csv_df, col, rel_min=0.0, rel_max=1.0):
    """
    Return list of (rel_start, rel_end) tuples where col == 1 (server is up).
    Handles the case where the whole run is 0 (returns empty list).
    """
    if col not in csv_df.columns:
        return []
    vals = csv_df[col].fillna(0).astype(int).values
    rels = csv_df["rel"].values
    spans = []
    in_span = False
    span_start = 0.0
    for k in range(len(vals)):
        if vals[k] == 1 and not in_span:
            in_span    = True
            span_start = rels[k]
        elif vals[k] == 0 and in_span:
            in_span = False
            spans.append((max(rel_min, span_start), min(rel_max, rels[k])))
    if in_span:
        spans.append((max(rel_min, span_start), rel_max))
    return [(max(rel_min, x0), min(rel_max, x1)) for x0, x1 in spans if x1 > rel_min and x0 < rel_max]


def draw_server_up_backdrop(ax, spans, yc, y_back, z_top, colour, label,
                             alpha_fill=SERVER_UP_ALPHA, alpha_edge=0.80):
    """
    Draw a full-height vertical backdrop wall for each server-up span.

    The wall sits at a fixed Y slightly behind the scenario's front face
    (y_back = yc - Y_DEPTH) and rises from Z=0 to z_top (= Z_MAX_LOAD +
    TTIME_BAND), so it is visible above AND behind the red load surface.

    For each span we draw:
      • A filled semi-transparent quad (the backdrop panel)
      • A solid coloured border on all 4 edges for crispness
      • A short label at the top-centre of the panel
    """
    if not spans:
        return

    for (x0, x1) in spans:
        # ── Filled panel ──────────────────────────────────────────────────────
        panel = [(x0, y_back, 0.0),
                 (x1, y_back, 0.0),
                 (x1, y_back, z_top),
                 (x0, y_back, z_top)]

        poly = Poly3DCollection([panel], zsort="average")
        poly.set_facecolor(colour)
        poly.set_alpha(alpha_fill)
        poly.set_edgecolor("none")
        poly.set_zorder(2)          # behind the red surface (zorder=5)
        ax.add_collection3d(poly)

        # ── Crisp coloured border lines ───────────────────────────────────────
        # Bottom edge
        ax.plot([x0, x1], [y_back, y_back], [0, 0],
                color=colour, linewidth=2.0, alpha=alpha_edge, zorder=3)
        # Top edge
        ax.plot([x0, x1], [y_back, y_back], [z_top, z_top],
                color=colour, linewidth=2.5, alpha=alpha_edge, zorder=3)
        # Left edge
        ax.plot([x0, x0], [y_back, y_back], [0, z_top],
                color=colour, linewidth=2.0, alpha=alpha_edge,
                linestyle="--", zorder=3)
        # Right edge
        ax.plot([x1, x1], [y_back, y_back], [0, z_top],
                color=colour, linewidth=2.0, alpha=alpha_edge,
                linestyle="--", zorder=3)

        # ── Label at top-centre of panel ──────────────────────────────────────
        x_mid = (x0 + x1) / 2.0
        ax.text(x_mid, y_back, z_top * 1.01,
                label,
                fontsize=FONT_SIZE - 14, color=colour, fontweight="bold",
                ha="center", va="bottom", zorder=4)


def main():
    n = len(FILE_PAIRS)
    datasets         = []
    global_ttime_max = 1.0

    for label, dpath, cpath in FILE_PAIRS:
        dat, t0, t1  = load_dat(dpath)
        csv_df       = load_csv(cpath, t0, t1)
        xg, load_pct = interp_load(csv_df["rel"].values, csv_df["avg_load_pct"].values)
        ttime_raw    = dat["ttime"].values.astype(float)
        ttime_rel    = dat["rel"].values
        global_ttime_max = max(global_ttime_max, ttime_raw.max())

        # Extract server-up spans directly from the raw (non-interpolated) CSV
        s2_spans = get_server_up_spans(csv_df, "server2_up")
        s3_spans = get_server_up_spans(csv_df, "server3_up")

        datasets.append(dict(
            label     = label,
            xg        = xg,
            load_pct  = load_pct,
            ttime_rel = ttime_rel,
            ttime_ms  = ttime_raw,
            s2_spans  = s2_spans,
            s3_spans  = s3_spans,
        ))

    y_positions = np.arange(n, dtype=float) * Y_SPACING

    # ── Build surface ─────────────────────────────────────────────────────────
    X, Y, Z = make_surface_arrays(datasets, y_positions)

    cmap_load = cm.get_cmap("Reds")
    norm_load = mcolors.Normalize(vmin=0, vmax=100)
    # Per-face colour: average of 4 quad corners
    Z_face      = (Z[:-1, :-1] + Z[:-1, 1:] + Z[1:, :-1] + Z[1:, 1:]) / 4.0
    face_colors = cmap_load(norm_load(Z_face))

    fig = plt.figure(figsize=(40, 20))
    # Disable computed z-order so explicit zorder for overlays is respected.
    ax  = fig.add_subplot(111, projection="3d", computed_zorder=False)

    # ── Main load surface ─────────────────────────────────────────────────────
    ax.plot_surface(
        X, Y, Z,
        facecolors  = face_colors,
        edgecolor   = "#FFFFFF",
        linewidth   = 0.45,
        shade       = False,          # must be False with explicit facecolors
        alpha       = 0.90,
        antialiased = True,
        zorder      = 5,
    )

    # ── Server-up backdrop walls ──────────────────────────────────────────────
    # Each server gets a full-height translucent wall drawn at y_back
    # (slightly behind the scenario's front face) so it rises above the
    # red load surface and is clearly visible for the full run duration.
    # Server 2 (green) sits closer; Server 3 (purple) sits further back
    # so both are visible simultaneously without occlusion.
    z_backdrop = Z_MAX_LOAD + TTIME_OFFSET + TTIME_BAND   # full plot height

    log_max = np.log1p(global_ttime_max)

    for i, (ds, yc) in enumerate(zip(datasets, y_positions)):
        y_back_s2 = yc - Y_SPACING * 0.10   # server2 wall: 30% behind front face
        y_back_s3 = yc - Y_SPACING * 0.20   # server3 wall: 55% behind (further)

        draw_server_up_backdrop(ax, ds["s2_spans"],
                                yc, y_back_s2, z_backdrop,
                                C_SERVER2, "srv2 up",
                                alpha_fill=SERVER_UP_ALPHA)
        draw_server_up_backdrop(ax, ds["s3_spans"],
                                yc, y_back_s3, z_backdrop,
                                C_SERVER3, "srv3 up",
                                alpha_fill=SERVER_UP_ALPHA)

        # ── ttime stems ───────────────────────────────────────────────────────
        trel   = ds["ttime_rel"]
        tms    = ds["ttime_ms"]
        t_norm = np.log1p(tms) / log_max * TTIME_BAND
        z_tips = Z_MAX_LOAD + TTIME_OFFSET + t_norm

        # Slightly nudge ttime overlay toward viewer so it does not sink into the surface.
        y_ttime = np.full(len(trel), yc - TTIME_Y_NUDGE)

        ax.scatter(trel, y_ttime, z_tips,
                   marker="x", s=TTIME_MARKER_SIZE, linewidths=TTIME_MARKER_LW,
                   color=C_TTIME, alpha=0.95, depthshade=False, zorder=11)

        order = np.argsort(trel)
        ax.plot(trel[order], y_ttime[order], z_tips[order],
            color=C_TTIME, linewidth=3.2, alpha=0.85, zorder=12)

    # ── Axis limits ───────────────────────────────────────────────────────────
    z_top = Z_MAX_LOAD + TTIME_OFFSET + TTIME_BAND + 2
    ax.set_xlim(0, 1)
    ax.set_ylim(y_positions[0] - 0.5, y_positions[-1] + 0.5)
    ax.set_zlim(0, z_top)

    ax.set_xticks(np.linspace(0, 1, 11))
    ax.set_xticklabels([f"{int(v*100)}%" for v in np.linspace(0, 1, 11)],
                       fontsize=FONT_SIZE - 4)

    ax.set_yticks(y_positions)
    ax.set_yticklabels([ds["label"] for ds in datasets], fontsize=FONT_SIZE - 2)

    # Z ticks: load % + ttime ms
    load_ticks  = [0, 25, 50, 75, 100]
    load_labels = [f"{v}%" for v in load_ticks]

    ttime_ticks_ms = ttime_tick_values(global_ttime_max)
    ttime_z_ticks  = [Z_MAX_LOAD + TTIME_OFFSET + (np.log1p(ms) / log_max) * TTIME_BAND
                      for ms in ttime_ticks_ms]
    ttime_labels   = [f"{int(ms):,} ms" for ms in ttime_ticks_ms]

    ax.set_zticks([float(v) for v in load_ticks] + ttime_z_ticks)
    ax.set_zticklabels(load_labels + ttime_labels, fontsize=FONT_SIZE - 5)

    ax.set_xlabel("Relative Time within Test Run", fontsize=FONT_SIZE, labelpad=38)
    ax.set_ylabel("Scenario",                      fontsize=FONT_SIZE, labelpad=38)
    ax.set_zlabel("Avg Load (%)  /  ttime (ms, log)",
                  fontsize=FONT_SIZE, labelpad=38)

    # ── Walls & grid ──────────────────────────────────────────────────────────
    for pane in (ax.xaxis.pane, ax.yaxis.pane, ax.zaxis.pane):
        pane.fill = True
        pane.set_facecolor(C_WALL)
        pane.set_edgecolor("#BFBFBF")
    ax.grid(True, linestyle="-", linewidth=0.7, color=C_GRID, alpha=0.75)

    # ── Legend ────────────────────────────────────────────────────────────────
    legend_elements = [
        Patch(facecolor=cmap_load(0.85), alpha=0.90, label="Avg CPU Load (%)"),
        Line2D([0], [0], color=C_TTIME, linewidth=3.2,  label="ttime (ms, log-scale)"),
        Line2D([0], [0], linestyle="None", marker="x", markersize=9,
               markeredgewidth=2, color=C_TTIME,        label="ttime datapoints"),
        Patch(facecolor=C_SERVER2, alpha=SERVER_UP_ALPHA, label="Server 2 up"),
        Patch(facecolor=C_SERVER3, alpha=SERVER_UP_ALPHA, label="Server 3 up"),
    ]
    ax.legend(handles=legend_elements, loc="upper left",
              fontsize=FONT_SIZE - 6, framealpha=0.92, edgecolor="#cccccc")

    # ── View & save ───────────────────────────────────────────────────────────
    ax.view_init(elev=25, azim=-50)
    fig.subplots_adjust(left=0.04, right=0.84, top=0.97, bottom=0.04)

    fig.savefig(OUTPUT_EPS, format="eps", dpi=300, bbox_inches="tight", pad_inches=0.50)
    fig.savefig(OUTPUT_PNG, format="png", dpi=200, bbox_inches="tight", pad_inches=0.50)
    print(f"Saved EPS : {OUTPUT_EPS}")
    print(f"Saved PNG : {OUTPUT_PNG}")
    plt.close(fig)


if __name__ == "__main__":
    main()