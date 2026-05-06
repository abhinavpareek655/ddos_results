import os
import sys
import re
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
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "graphs")
EXPERIMENT = sys.argv[1] if len(sys.argv) > 1 else "ac+filtering"

FILE_PAIRS = [
    ("c50",      os.path.join(BENIGN_DIR, EXPERIMENT, "c50/a.dat"),      os.path.join(SERVER_DIR, EXPERIMENT, "c50/haproxy-metrics.csv"),      os.path.join(BENIGN_DIR, EXPERIMENT, "c50/a.txt")),
    ("c100",     os.path.join(BENIGN_DIR, EXPERIMENT, "c100/a.dat"),     os.path.join(SERVER_DIR, EXPERIMENT, "c100/haproxy-metrics.csv"),     os.path.join(BENIGN_DIR, EXPERIMENT, "c100/a.txt")),
    ("c500",     os.path.join(BENIGN_DIR, EXPERIMENT, "c500/a.dat"),     os.path.join(SERVER_DIR, EXPERIMENT, "c500/haproxy-metrics.csv"),     os.path.join(BENIGN_DIR, EXPERIMENT, "c500/a.txt")),
    ("c1000",    os.path.join(BENIGN_DIR, EXPERIMENT, "c1000/a.dat"),    os.path.join(SERVER_DIR, EXPERIMENT, "c1000/haproxy-metrics.csv"),    os.path.join(BENIGN_DIR, EXPERIMENT, "c1000/a.txt")),
    ("spoofing", os.path.join(BENIGN_DIR, EXPERIMENT, "spoofing/a.dat"), os.path.join(SERVER_DIR, EXPERIMENT, "spoofing/haproxy-metrics.csv"), os.path.join(BENIGN_DIR, EXPERIMENT, "spoofing/a.txt")),
]

OUTPUT_EPS = os.path.join(OUTPUT_DIR, f"{EXPERIMENT}.eps")
OUTPUT_PNG = os.path.join(OUTPUT_DIR, f"{EXPERIMENT}.png")

# ── LAYOUT ───────────────────────────────────────────────────────────────────
N_X          = 60
N_Y_PER_SCN  = 3
Y_SPACING    = 2.0
FONT_SIZE    = 52        # unified font size for ALL text

Z_MAX_LOAD   = 100.0
TTIME_BAND   = 80.0
TTIME_OFFSET = 15.0

C_TTIME   = "#2196F3"
C_WALL    = "#F5F5F5"
C_GRID    = "#545454"
C_SERVER2 = "#2ECC71"
C_SERVER3 = "#9B59B6"

TTIME_MARKER_SIZE = 40
TTIME_MARKER_LW   = 2.0
N_TTIME_TICKS     = 5
TTIME_Y_NUDGE     = 0.08

SERVER_UP_ALPHA = 0.02
EPS_BG_BLEND    = 0.35

matplotlib.rcParams.update({
    "font.family":     "serif",
    "font.serif":      ["Times New Roman", "Times", "DejaVu Serif", "serif"],
    "font.size":       FONT_SIZE,
    "axes.labelsize":  FONT_SIZE,
    "xtick.labelsize": FONT_SIZE,
    "ytick.labelsize": FONT_SIZE,
    "axes.linewidth":  1.2,
})

# ── AB PARSER ────────────────────────────────────────────────────────────────

def parse_ab_txt(path):
    result = {"mean_ms": None, "max_ms": None}
    try:
        with open(path) as fh:
            text = fh.read()
        m = re.search(
            r"^Total:\s+(\d+)\s+(\d+)\s+\S+\s+(\d+)\s+(\d+)",
            text, re.MULTILINE
        )
        if m:
            result["mean_ms"] = int(m.group(2))
            result["max_ms"]  = int(m.group(4))
    except FileNotFoundError:
        pass
    return result

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
    if "avg_load_pct" in df.columns:
        df["avg_load_pct"] = (
            pd.to_numeric(df["avg_load_pct"], errors="coerce")
              .interpolate(method="index", limit_direction="both")
              .clip(0.0, 100.0)
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
    return [(max(rel_min, x0), min(rel_max, x1))
            for x0, x1 in spans if x1 > rel_min and x0 < rel_max]


def blend_with_white(hex_colour, blend):
    rgb = np.array(mcolors.to_rgb(hex_colour))
    return tuple((1.0 - blend) * rgb + blend * np.array([1.0, 1.0, 1.0]))


def draw_server_up_backdrop(ax, spans, yc, y_back, z_top, colour, label,
                             alpha_fill=0.03, alpha_edge=1.00):
    if not spans:
        return
    fill_colour = colour
    label_placed = False
    for (x0, x1) in spans:
        panel = [(x0, y_back, 0.0), (x1, y_back, 0.0),
                 (x1, y_back, z_top), (x0, y_back, z_top)]
        poly = Poly3DCollection([panel], zsort="max")
        poly.set_facecolor(fill_colour)
        poly.set_alpha(alpha_fill)
        poly.set_edgecolor("none")
        poly.set_zorder(3)
        ax.add_collection3d(poly)
        ax.plot([x0, x1], [y_back, y_back], [0, 0],
        color=fill_colour, linewidth=2.0, alpha=alpha_edge, zorder=2)
        ax.plot([x0, x1], [y_back, y_back], [z_top, z_top],
        color=fill_colour, linewidth=2.5, alpha=alpha_edge, zorder=2)
        ax.plot([x0, x0], [y_back, y_back], [0, z_top],
        color=fill_colour, linewidth=2.0, alpha=alpha_edge,
        linestyle="--", zorder=2)
        ax.plot([x1, x1], [y_back, y_back], [0, z_top],
        color=fill_colour, linewidth=2.0, alpha=alpha_edge,
        linestyle="--", zorder=2)
        if not label_placed:
            x_mid = (x0 + x1) / 2.0
            ax.text(x_mid, y_back, z_top * 1.01, label,
            fontsize=FONT_SIZE * 0.8, color=fill_colour, fontweight="bold",
            ha="center", va="bottom", zorder=22, alpha=1.0)
            label_placed = True


TABLE_FS = 38
TABLE_X = 0.61
TABLE_Y = 0.82

COLUMNS = [
    ("Scenario",  10),
    ("Mean (ms)", 8),
    ("Max (ms)",  8),
]

def fmt(val):
    return f"{int(val):,}" if val is not None else "N/A"

def add_table(fig, datasets):
    FIG_WIDTH_PT = 40 * 72
    pt_per_char = TABLE_FS * 0.6
    col_widths_frac = [(chars * pt_per_char) / FIG_WIDTH_PT for _, chars in COLUMNS]
    total_w = sum(col_widths_frac)

    FIG_HEIGHT_PT = 20 * 72
    row_height_pt = TABLE_FS * 1.1
    n_rows = len(datasets) + 1
    total_h = (n_rows * row_height_pt) / FIG_HEIGHT_PT

    tax = fig.add_axes([TABLE_X, TABLE_Y, total_w, total_h])
    tax.axis("off")

    col_labels = [col[0] for col in COLUMNS]
    row_data = [[ds["label"], fmt(ds["ab"]["mean_ms"]), fmt(ds["ab"]["max_ms"])] for ds in datasets]

    tbl = tax.table(
        cellText=row_data,
        colLabels=col_labels,
        colWidths=[w / total_w for w in col_widths_frac],
        loc="center",
        bbox=[0.0, 0.0, 1.0, 1.0],
    )
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(TABLE_FS)

    n_cols = len(col_labels)

    for c in range(n_cols):
        cell = tbl[0, c]
        cell.set_facecolor("#37474F")
        cell.set_text_props(color="white", fontweight="bold")
        cell.set_edgecolor("#888888")

    for r in range(1, len(row_data) + 1):
        bg = "#F0F0F0" if r % 2 == 0 else "#FFFFFF"
        for c in range(n_cols):
            cell = tbl[r, c]
            cell.set_facecolor(bg)
            cell.set_edgecolor("#CCCCCC")
            if c > 0:
                cell.get_text().set_ha("right")


# ── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    datasets         = []
    global_ttime_max = 1.0

    for label, dpath, cpath, abpath in FILE_PAIRS:
        dat, t0, t1  = load_dat(dpath)
        csv_df       = load_csv(cpath, t0, t1)
        xg, load_pct = interp_load(csv_df["rel"].values, csv_df["avg_load_pct"].values)
        ttime_raw    = dat["ttime"].values.astype(float)
        ttime_rel    = dat["rel"].values
        global_ttime_max = max(global_ttime_max, ttime_raw.max())

        s2_spans = get_server_up_spans(csv_df, "server2_up")
        s3_spans = get_server_up_spans(csv_df, "server3_up")
        ab_stats = parse_ab_txt(abpath)

        datasets.append(dict(
            label     = label,
            xg        = xg,
            load_pct  = load_pct,
            ttime_rel = ttime_rel,
            ttime_ms  = ttime_raw,
            s2_spans  = s2_spans,
            s3_spans  = s3_spans,
            ab        = ab_stats,
        ))

    y_positions = np.arange(len(datasets), dtype=float) * Y_SPACING
    X, Y, Z    = make_surface_arrays(datasets, y_positions)

    cmap_load = cm.get_cmap("Reds")
    norm_load = mcolors.Normalize(vmin=0, vmax=100)
    Z_face      = (Z[:-1, :-1] + Z[:-1, 1:] + Z[1:, :-1] + Z[1:, 1:]) / 4.0
    face_colors = cmap_load(norm_load(Z_face))

    fig = plt.figure(figsize=(40, 20))
    ax  = fig.add_subplot(111, projection="3d", computed_zorder=False)

    is_eps = OUTPUT_EPS.lower().endswith(".eps")
    server2_fill      = blend_with_white(C_SERVER2, EPS_BG_BLEND) if is_eps else C_SERVER2
    server3_fill      = blend_with_white(C_SERVER3, EPS_BG_BLEND) if is_eps else C_SERVER3
    server_wall_alpha = 1.0 if is_eps else SERVER_UP_ALPHA

    ax.plot_surface(
        X, Y, Z,
        facecolors=face_colors, edgecolor="#FFFFFF",
        linewidth=0.45, shade=False, alpha=0.90,
        antialiased=True, zorder=5,
    )

    z_backdrop = Z_MAX_LOAD + TTIME_OFFSET + TTIME_BAND
    log_max    = np.log1p(global_ttime_max)

    for i, (ds, yc) in enumerate(zip(datasets, y_positions)):
        y_back_s2 = yc - Y_SPACING * 0.10
        y_back_s3 = yc - Y_SPACING * 0.20

        draw_server_up_backdrop(ax, ds["s2_spans"], yc, y_back_s2, z_backdrop,
                                server2_fill, "srv2 up")
        draw_server_up_backdrop(ax, ds["s3_spans"], yc, y_back_s3, z_backdrop,
                                server3_fill, "srv3 up")

        trel    = ds["ttime_rel"]
        tms     = ds["ttime_ms"]
        t_norm  = np.log1p(tms) / log_max * TTIME_BAND
        z_tips  = Z_MAX_LOAD + TTIME_OFFSET + t_norm
        y_ttime = np.full(len(trel), yc - TTIME_Y_NUDGE)

        ax.scatter(trel, y_ttime, z_tips,
                   marker="x", s=TTIME_MARKER_SIZE, linewidths=TTIME_MARKER_LW,
                   color=C_TTIME, alpha=0.95, depthshade=False, zorder=11)
        order = np.argsort(trel)
        ax.plot(trel[order], y_ttime[order], z_tips[order],
                color=C_TTIME, linewidth=3.2, alpha=0.85, zorder=12)

    z_top = Z_MAX_LOAD + TTIME_OFFSET + TTIME_BAND + 2
    ax.set_xlim(0, 1)
    ax.set_ylim(y_positions[0] - 0.5, y_positions[-1] + 0.5)
    ax.set_zlim(0, z_top)

    ax.set_xticks(np.linspace(0, 1, 11))
    ax.set_xticklabels([f"{int(v*100)}%" for v in np.linspace(0, 1, 11)],
                       fontsize=FONT_SIZE, 
                       rotation=45,
                       ha="right",
                       va="center",
                       rotation_mode="anchor",)
    ax.set_yticks(y_positions)
    ax.set_yticklabels(
        [ds["label"] for ds in datasets],
        fontsize=FONT_SIZE,
        rotation=-30,
        ha="left",
        va="center",
        rotation_mode="anchor",
    )
    ax.tick_params(axis="y", pad=10)

    load_ticks     = [0, 25, 50, 75, 100]
    load_labels    = [f"{v}%" for v in load_ticks]
    ttime_ticks_ms = ttime_tick_values(global_ttime_max)
    ttime_z_ticks  = [Z_MAX_LOAD + TTIME_OFFSET + (np.log1p(ms) / log_max) * TTIME_BAND
                      for ms in ttime_ticks_ms]
    ttime_labels   = [f"{int(ms):,} ms" for ms in ttime_ticks_ms]
    ax.set_zticks([float(v) for v in load_ticks] + ttime_z_ticks)
    ax.set_zticklabels(
        load_labels + ttime_labels, 
        fontsize=FONT_SIZE,
        ha="left",
        va="center",
        rotation_mode="anchor",
        )
    ax.tick_params(axis="z", pad=5);

    ax.set_xlabel("Relative Time within Test Run", fontsize=FONT_SIZE, labelpad=90)
    ax.set_ylabel("Scenario",                      fontsize=FONT_SIZE, labelpad=90)
    ax.set_zlabel("Avg Load / ttime",
                  fontsize=FONT_SIZE, labelpad=90)

    for pane in (ax.xaxis.pane, ax.yaxis.pane, ax.zaxis.pane):
        pane.fill = True
        pane.set_facecolor(C_WALL)
        pane.set_edgecolor("#BFBFBF")
    ax.grid(True, linestyle="-", linewidth=0.7, color=C_GRID, alpha=0.75)
    ax.view_init(elev=25, azim=-50)

    add_table(fig, datasets)

    # Full bleed — table floats inside via add_axes
    fig.subplots_adjust(left=0.02, right=0.98, top=0.98, bottom=0.02)

    fig.savefig(OUTPUT_EPS, format="eps", dpi=300, bbox_inches="tight", pad_inches=0.15)
    fig.savefig(OUTPUT_PNG, format="png", dpi=200, bbox_inches="tight", pad_inches=0.15)
    print(f"Saved EPS : {OUTPUT_EPS}")
    print(f"Saved PNG : {OUTPUT_PNG}")
    plt.close(fig)


if __name__ == "__main__":
    main()