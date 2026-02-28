"""
AS7343 Real-Time Spectral Plotter — Full Channel Display
Matches CSV output from main.cpp (PlatformIO firmware)

CSV column order:
  timestamp_ms,
  F1_405nm, F2_425nm, FZ_450nm, F3_475nm, F4_515nm, F5_550nm,
  FY_555nm, FXL_600nm, F6_640nm, F7_690nm, F8_745nm, NIR_855nm,
  VIS_clear, R_approx, G_approx, B_approx

Usage:
  python spectral_plotter.py            # defaults to COM5 / /dev/ttyUSB0
  python spectral_plotter.py COM3
  python spectral_plotter.py /dev/ttyACM0

Requirements:
  pip install pyserial matplotlib numpy
"""

import sys
import serial
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import matplotlib.patches as mpatches
import matplotlib.ticker as ticker
import numpy as np
from collections import deque
import time

# ── Config ────────────────────────────────────────────────────────────────────

PORT        = sys.argv[1] if len(sys.argv) > 1 else ("COM5" if sys.platform == "win32" else "/dev/ttyUSB0")
BAUD        = 115200
HISTORY_LEN = 120   # rolling history length (frames)
SAVE_CSV    = True  # set False to disable saving
CSV_FILE    = "spectral_log.csv"

# ── Channel definitions ───────────────────────────────────────────────────────
# (csv_index, label, wavelength_nm, hex_color)
CHANNELS = [
    (0,  "F1",  405, "#9B30FF"),
    (1,  "F2",  425, "#6A0FFF"),
    (2,  "FZ",  450, "#1E3FFF"),
    (3,  "F3",  475, "#0094FF"),
    (4,  "F4",  515, "#00C44F"),
    (5,  "F5",  550, "#7ED600"),
    (6,  "FY",  555, "#AADD00"),
    (7,  "FXL", 600, "#FF9900"),
    (8,  "F6",  640, "#FF2200"),
    (9,  "F7",  690, "#CC0000"),
    (10, "F8",  745, "#880000"),
    (11, "NIR", 855, "#440033"),
]

IDX_VIS = 12
IDX_R   = 13
IDX_G   = 14
IDX_B   = 15

LABELS  = [f"{lbl}\n{wl}nm" for _, lbl, wl, _ in CHANNELS]
COLORS  = [c for _, _, _, c in CHANNELS]
N_CH    = len(CHANNELS)
x_pos   = np.arange(N_CH)

# ── Serial ────────────────────────────────────────────────────────────────────

print(f"Connecting to {PORT} @ {BAUD} baud ...")
try:
    ser = serial.Serial(PORT, BAUD, timeout=1)
except serial.SerialException as e:
    print(f"ERROR: {e}")
    sys.exit(1)
print("Connected. Waiting for data ...\n")

# ── CSV logging ───────────────────────────────────────────────────────────────

csv_file = None
if SAVE_CSV:
    csv_file = open(CSV_FILE, "w")
    csv_file.write("timestamp_ms,"
                   "F1_405nm,F2_425nm,FZ_450nm,F3_475nm,"
                   "F4_515nm,F5_550nm,FY_555nm,FXL_600nm,"
                   "F6_640nm,F7_690nm,F8_745nm,NIR_855nm,"
                   "VIS_clear,R_approx,G_approx,B_approx\n")
    print(f"Logging to {CSV_FILE}")

# ── History buffers ───────────────────────────────────────────────────────────

history  = {idx: deque([0.0] * HISTORY_LEN, maxlen=HISTORY_LEN) for idx, *_ in CHANNELS}
vis_hist = deque([0.0] * HISTORY_LEN, maxlen=HISTORY_LEN)

last_vals = {idx: 0.0 for idx, *_ in CHANNELS}
last_R = last_G = last_B = last_VIS = 0.0

# ── Figure ────────────────────────────────────────────────────────────────────

plt.style.use("dark_background")
fig = plt.figure(figsize=(16, 10), facecolor="#080808")
fig.canvas.manager.set_window_title("AS7343 — Full Spectral Monitor")

gs = gridspec.GridSpec(
    4, 3,
    figure=fig,
    left=0.06, right=0.97,
    top=0.91,  bottom=0.07,
    hspace=0.65, wspace=0.38,
)

ax_bar   = fig.add_subplot(gs[0:2, 0:2])   # main bar chart — wide
ax_rgb   = fig.add_subplot(gs[0:2, 2])     # colour swatch
ax_trend = fig.add_subplot(gs[2:4, 0:2])   # all-channel trend
ax_vis   = fig.add_subplot(gs[2:4, 2])     # VIS broadband + stats

def style_ax(ax, title, ylabel):
    ax.set_facecolor("#0e0e0e")
    ax.set_title(title, fontsize=10, color="#dddddd", pad=5, fontweight="bold")
    ax.set_ylabel(ylabel, fontsize=8, color="#999999")
    ax.tick_params(colors="#777777", labelsize=7.5)
    for sp in ax.spines.values():
        sp.set_edgecolor("#2a2a2a")

# ── Bar chart ─────────────────────────────────────────────────────────────────

bars = ax_bar.bar(x_pos, [0] * N_CH, color=COLORS,
                  width=0.65, edgecolor="#00000055", linewidth=0.8, zorder=3)
ax_bar.set_xticks(x_pos)
ax_bar.set_xticklabels(LABELS, fontsize=7.5, rotation=0, ha="center")
style_ax(ax_bar, "Live Spectrum — All 12 Spectral Channels", "ADC counts")

# Value labels above each bar
bar_val_texts = [
    ax_bar.text(xi, 0, "", ha="center", va="bottom",
                fontsize=7, color="#cccccc", zorder=5)
    for xi in x_pos
]

# Smooth envelope line
env_x = np.linspace(0, N_CH - 1, 300)
env_line, = ax_bar.plot([], [], color="#ffffff30", linewidth=1.5, zorder=2)
env_fill_container = [None]

# Peak indicator
peak_marker, = ax_bar.plot([], [], marker="v", color="#ffdd00",
                            markersize=8, linestyle="none", zorder=6)
peak_text = ax_bar.text(0, 0, "", ha="center", va="top",
                         fontsize=8, color="#ffdd00", fontweight="bold", zorder=6)

# ── Colour swatch ─────────────────────────────────────────────────────────────

ax_rgb.set_facecolor("#0e0e0e")
ax_rgb.set_title("Approximate Object Colour", fontsize=10,
                  color="#dddddd", pad=5, fontweight="bold")
ax_rgb.set_xlim(0, 1)
ax_rgb.set_ylim(0, 1)
ax_rgb.set_xticks([])
ax_rgb.set_yticks([])
for sp in ax_rgb.spines.values():
    sp.set_edgecolor("#2a2a2a")

def make_swatch(ax, xy, wh, ec="#444444"):
    p = mpatches.FancyBboxPatch(xy, *wh,
        boxstyle="round,pad=0.02", facecolor=(0,0,0),
        edgecolor=ec, linewidth=1.0,
        transform=ax.transAxes, clip_on=False)
    ax.add_patch(p)
    return p

swatch_main = make_swatch(ax_rgb, (0.08, 0.32), (0.84, 0.52), "#555555")
swatch_r    = make_swatch(ax_rgb, (0.08, 0.14), (0.24, 0.13))
swatch_g    = make_swatch(ax_rgb, (0.38, 0.14), (0.24, 0.13))
swatch_b    = make_swatch(ax_rgb, (0.68, 0.14), (0.24, 0.13))

rgb_label = ax_rgb.text(0.5, 0.88, "R=0  G=0  B=0",
    transform=ax_rgb.transAxes, ha="center", va="center",
    fontsize=9, color="#cccccc", fontweight="bold")
vis_label = ax_rgb.text(0.5, 0.05, "VIS = 0",
    transform=ax_rgb.transAxes, ha="center", va="bottom",
    fontsize=8.5, color="#666666")
for x_lbl, ch_lbl in zip([0.20, 0.50, 0.80], ["R", "G", "B"]):
    ax_rgb.text(x_lbl, 0.21, ch_lbl, transform=ax_rgb.transAxes,
                ha="center", va="center", fontsize=7, color="#888888")

# ── All-channel trend ─────────────────────────────────────────────────────────

style_ax(ax_trend, f"All Channels — Rolling History ({HISTORY_LEN} frames)", "ADC counts")
ax_trend.set_xlabel("Frame", fontsize=8, color="#777777")
t_x = list(range(HISTORY_LEN))
trend_lines = {}
for idx, lbl, wl, col in CHANNELS:
    (ln,) = ax_trend.plot(t_x, list(history[idx]),
                          color=col, linewidth=1.1, alpha=0.9,
                          label=f"{lbl} {wl}nm")
    trend_lines[idx] = ln

ax_trend.legend(
    loc="upper left", fontsize=6.5, framealpha=0.3,
    labelcolor="white", facecolor="#111111",
    ncol=4, handlelength=1.2, columnspacing=0.8
)

# ── VIS trend + stats ─────────────────────────────────────────────────────────

style_ax(ax_vis, "VIS Broadband Trend", "ADC counts")
ax_vis.set_xlabel("Frame", fontsize=8, color="#777777")
vis_line, = ax_vis.plot(t_x, list(vis_hist), color="#bbbbbb", linewidth=1.3)
vis_fill_container = [ax_vis.fill_between(t_x, list(vis_hist),
                                           alpha=0.12, color="#bbbbbb")]

stats_text = ax_vis.text(0.97, 0.97, "",
    transform=ax_vis.transAxes, ha="right", va="top",
    fontsize=7.5, color="#aaaaaa",
    bbox=dict(facecolor="#111111", edgecolor="#333333",
              boxstyle="round,pad=0.4", alpha=0.85))

# ── Status bar ────────────────────────────────────────────────────────────────

status_text = fig.text(0.5, 0.965, "Waiting for data...",
    ha="center", va="top", fontsize=11,
    color="#cccccc", fontweight="bold")

plt.ion()
plt.show()

# ── Parsing ───────────────────────────────────────────────────────────────────

def parse_line(line):
    if not line or line.startswith("#") or "timestamp" in line:
        return None
    parts = line.split(",")
    if len(parts) < 17:
        return None
    try:
        return int(parts[0]), [float(p) for p in parts[1:]]
    except ValueError:
        return None

# ── Main loop ─────────────────────────────────────────────────────────────────

frame_count = 0
t_start     = time.time()

try:
    while True:
        raw    = ser.readline().decode(errors="ignore").strip()
        parsed = parse_line(raw)
        if parsed is None:
            continue

        ts, data = parsed

        if csv_file:
            csv_file.write(raw + "\n")
            csv_file.flush()

        # Update state
        for idx, *_ in CHANNELS:
            last_vals[idx] = data[idx]
            history[idx].append(data[idx])

        last_R   = data[IDX_R]
        last_G   = data[IDX_G]
        last_B   = data[IDX_B]
        last_VIS = data[IDX_VIS]
        vis_hist.append(last_VIS)

        # ── Bar chart ─────────────────────────────────────────────────────────
        cur_vals = [last_vals[idx] for idx, *_ in CHANNELS]
        max_val  = max(max(cur_vals), 1)
        peak_idx = int(np.argmax(cur_vals))

        for bar, h, txt in zip(bars, cur_vals, bar_val_texts):
            bar.set_height(h)
            txt.set_position((bar.get_x() + bar.get_width() / 2, h * 1.02))
            txt.set_text(str(int(h)))

        ax_bar.set_ylim(0, max_val * 1.35)

        # Envelope
        interp_y = np.interp(env_x, x_pos, cur_vals)
        env_line.set_data(env_x, interp_y)
        if env_fill_container[0] is not None:
            env_fill_container[0].remove()
        env_fill_container[0] = ax_bar.fill_between(
            env_x, interp_y, alpha=0.07, color="#ffffff", zorder=1)

        # Peak marker
        peak_marker.set_data([peak_idx], [max_val * 1.22])
        peak_text.set_position((peak_idx, max_val * 1.32))
        peak_text.set_text(f"Peak: {CHANNELS[peak_idx][1]} {CHANNELS[peak_idx][2]}nm = {int(max_val)}")

        # ── Colour swatch ─────────────────────────────────────────────────────
        denom = max(last_R, last_G, last_B, 1.0)
        nr, ng, nb = last_R / denom, last_G / denom, last_B / denom
        swatch_main.set_facecolor((nr, ng, nb))
        swatch_r.set_facecolor((nr, 0, 0))
        swatch_g.set_facecolor((0, ng, 0))
        swatch_b.set_facecolor((0, 0, nb))
        rgb_label.set_text(f"R={last_R:.0f}  G={last_G:.0f}  B={last_B:.0f}")
        vis_label.set_text(f"VIS = {last_VIS:.0f}")

        # ── All-channel trend ─────────────────────────────────────────────────
        trend_max = 1
        for idx, *_ in CHANNELS:
            ydata = list(history[idx])
            trend_lines[idx].set_ydata(ydata)
            trend_max = max(trend_max, max(ydata))
        ax_trend.set_ylim(0, trend_max * 1.15)

        # ── VIS trend ─────────────────────────────────────────────────────────
        vis_data = list(vis_hist)
        vis_line.set_ydata(vis_data)
        vis_fill_container[0].remove()
        vis_fill_container[0] = ax_vis.fill_between(
            t_x, vis_data, alpha=0.12, color="#bbbbbb")
        ax_vis.set_ylim(0, max(max(vis_data), 1) * 1.20)

        vis_arr = np.array(vis_data)
        stats_text.set_text(
            f"min   {vis_arr.min():.0f}\n"
            f"max   {vis_arr.max():.0f}\n"
            f"mean {vis_arr.mean():.1f}\n"
            f"std    {vis_arr.std():.1f}"
        )

        # ── Status ────────────────────────────────────────────────────────────
        frame_count += 1
        fps = frame_count / (time.time() - t_start)
        status_text.set_text(
            f"AS7343  |  t = {ts/1000:.1f} s  |  "
            f"Peak: {CHANNELS[peak_idx][1]} {CHANNELS[peak_idx][2]}nm = {int(max_val)}  |  "
            f"VIS = {last_VIS:.0f}  |  "
            f"Frame {frame_count}  ({fps:.1f} fps)"
            + ("  [saving]" if csv_file else "")
        )

        fig.canvas.draw()
        fig.canvas.flush_events()

except KeyboardInterrupt:
    print("\nStopped by user.")
finally:
    ser.close()
    if csv_file:
        csv_file.close()
        print(f"Data saved to {CSV_FILE}")
    print("Serial port closed.")