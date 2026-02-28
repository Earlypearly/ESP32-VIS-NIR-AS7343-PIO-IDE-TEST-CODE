"""
AS7343 Real-Time Spectral Plotter
Matches CSV output from main.cpp (PlatformIO firmware)

CSV column order:
  timestamp_ms,
  F1_405nm, F2_425nm, FZ_450nm, F3_475nm, F4_515nm, F5_550nm,
  FY_555nm, FXL_600nm, F6_640nm, F7_690nm, F8_745nm, NIR_855nm,
  VIS_clear, R_approx, G_approx, B_approx

LED is always ON — continuous mode, no ambient subtraction.

Usage:
  python spectral_plotter.py            # uses COM5 / /dev/ttyUSB0 default
  python spectral_plotter.py COM3
  python spectral_plotter.py /dev/ttyACM0

Requirements:
  pip install pyserial matplotlib
"""

import sys
import serial
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.gridspec as gridspec
from collections import deque
import time

# ── Config ────────────────────────────────────────────────────────────────────

PORT        = sys.argv[1] if len(sys.argv) > 1 else ("COM5" if sys.platform == "win32" else "/dev/ttyUSB0")
BAUD        = 115200
HISTORY_LEN = 60   # number of past readings shown in the trend lines

# ── Channel definitions (wavelength order, matching firmware CSV) ─────────────
# (data_field_index, label, wavelength_nm, RGB_color)
# data_field_index is 0-based after timestamp and LED_state columns

CHANNELS = [
    (0,  "F1",  405, (0.45, 0.00, 0.90)),   # violet
    (1,  "F2",  425, (0.25, 0.00, 1.00)),   # violet-blue
    (2,  "FZ",  450, (0.00, 0.20, 1.00)),   # blue
    (3,  "F3",  475, (0.00, 0.60, 1.00)),   # blue-cyan
    (4,  "F4",  515, (0.00, 0.85, 0.30)),   # green
    (5,  "F5",  550, (0.40, 0.95, 0.00)),   # green-yellow
    (6,  "FY",  555, (0.60, 1.00, 0.00)),   # yellow-green
    (7,  "FXL", 600, (1.00, 0.65, 0.00)),   # orange
    (8,  "F6",  640, (1.00, 0.20, 0.00)),   # red
    (9,  "F7",  690, (0.85, 0.00, 0.00)),   # deep red
    (10, "F8",  745, (0.55, 0.00, 0.00)),   # near-IR
    (11, "NIR", 855, (0.30, 0.00, 0.20)),   # NIR
]

# CSV data-field indices for derived channels
IDX_VIS = 12
IDX_R   = 13
IDX_G   = 14
IDX_B   = 15

# ── Serial connection ─────────────────────────────────────────────────────────

print(f"Connecting to {PORT} @ {BAUD} baud ...")
try:
    ser = serial.Serial(PORT, BAUD, timeout=1)
except serial.SerialException as e:
    print(f"ERROR: {e}")
    sys.exit(1)
print("Connected. Waiting for data ...\n")

# ── History buffers ───────────────────────────────────────────────────────────

history     = {idx: deque([0.0] * HISTORY_LEN, maxlen=HISTORY_LEN) for idx, *_ in CHANNELS}
ts_history  = deque([0.0] * HISTORY_LEN, maxlen=HISTORY_LEN)

last_vals = {idx: 0 for idx, *_ in CHANNELS}
last_R = last_G = last_B = last_VIS = 0.0

# ── Figure layout ─────────────────────────────────────────────────────────────

plt.style.use("dark_background")
fig = plt.figure(figsize=(14, 9), facecolor="#0d0d0d")
fig.canvas.manager.set_window_title("AS7343 Live Spectral Monitor")

gs = gridspec.GridSpec(
    3, 2,
    figure=fig,
    left=0.07, right=0.97,
    top=0.88,  bottom=0.10,
    hspace=0.55, wspace=0.35,
)

ax_bar   = fig.add_subplot(gs[0:2, 0])   # main spectrum bar chart
ax_diff  = fig.add_subplot(gs[2,   0])   # LED-on minus ambient
ax_trend = fig.add_subplot(gs[0:2, 1])   # rolling trend lines
ax_rgb   = fig.add_subplot(gs[2,   1])   # RGB colour swatch

bar_labels = [f"{lbl}\n{wl}nm" for _, lbl, wl, _ in CHANNELS]
bar_colors = [c for *_, c in CHANNELS]
x_pos      = list(range(len(CHANNELS)))

# ── Bar chart (LED ON spectrum) ───────────────────────────────────────────────
bars_on = ax_bar.bar(x_pos, [0] * len(CHANNELS), color=bar_colors,
                     width=0.6, edgecolor="#ffffff22", linewidth=0.5)
ax_bar.set_xticks(x_pos)
ax_bar.set_xticklabels(bar_labels, fontsize=7.5, rotation=45, ha="right")
ax_bar.set_ylabel("ADC counts", fontsize=9, color="#cccccc")
ax_bar.set_title("Live Spectrum (LED ON)", fontsize=11, color="#ffffff", pad=6)
ax_bar.tick_params(colors="#aaaaaa", labelsize=8)
ax_bar.set_facecolor("#111111")
for sp in ax_bar.spines.values():
    sp.set_edgecolor("#333333")

# ── Difference chart (ON - ambient) ──────────────────────────────────────────
bars_diff = ax_diff.bar(x_pos, [0] * len(CHANNELS), color=bar_colors,
                        width=0.6, edgecolor="#ffffff22", linewidth=0.5)
ax_diff.set_xticks(x_pos)
ax_diff.set_xticklabels(bar_labels, fontsize=7.5, rotation=45, ha="right")
ax_diff.set_ylabel("ON - ambient", fontsize=9, color="#cccccc")
ax_diff.set_title("Frame-to-frame delta (current - previous)", fontsize=9, color="#aaaaaa", pad=4)
ax_diff.axhline(0, color="#555555", linewidth=0.8)
ax_diff.tick_params(colors="#aaaaaa", labelsize=8)
ax_diff.set_facecolor("#111111")
for sp in ax_diff.spines.values():
    sp.set_edgecolor("#333333")

# ── Trend lines ───────────────────────────────────────────────────────────────
ax_trend.set_facecolor("#111111")
ax_trend.set_title(f"Rolling trend (last {HISTORY_LEN} LED-ON readings)", fontsize=10,
                   color="#ffffff", pad=6)
ax_trend.set_ylabel("ADC counts", fontsize=9, color="#cccccc")
ax_trend.tick_params(colors="#aaaaaa", labelsize=8)
for sp in ax_trend.spines.values():
    sp.set_edgecolor("#333333")

t_x = list(range(HISTORY_LEN))
# Subset of channels for legible trend plot
TREND_INDICES = [0, 2, 4, 6, 8, 10, 11]   # F1, FZ, F4, FY, F6, F8, NIR
trend_lines = {}
for idx, lbl, wl, col in CHANNELS:
    if idx in TREND_INDICES:
        (ln,) = ax_trend.plot(t_x, list(history[idx]),
                              color=col, linewidth=1.4, alpha=0.9,
                              label=f"{lbl} {wl}nm")
        trend_lines[idx] = ln

ax_trend.legend(loc="upper left", fontsize=7, framealpha=0.25,
                labelcolor="white", facecolor="#1a1a1a")

# ── RGB swatch ────────────────────────────────────────────────────────────────
ax_rgb.set_facecolor("#111111")
ax_rgb.set_xlim(0, 1)
ax_rgb.set_ylim(0, 1)
ax_rgb.set_xticks([])
ax_rgb.set_yticks([])
ax_rgb.set_title("Approximate object colour", fontsize=10, color="#ffffff", pad=6)
for sp in ax_rgb.spines.values():
    sp.set_edgecolor("#333333")

swatch = mpatches.FancyBboxPatch((0.05, 0.15), 0.9, 0.70,
                                  boxstyle="round,pad=0.02",
                                  facecolor=(0, 0, 0), edgecolor="#555555",
                                  linewidth=1.5, transform=ax_rgb.transAxes,
                                  clip_on=False)
ax_rgb.add_patch(swatch)

rgb_text = ax_rgb.text(0.5, 0.08, "R=0  G=0  B=0",
                        transform=ax_rgb.transAxes, ha="center", va="bottom",
                        fontsize=9, color="#aaaaaa")
vis_text = ax_rgb.text(0.5, 0.93, "VIS=0",
                        transform=ax_rgb.transAxes, ha="center", va="top",
                        fontsize=9, color="#777777")

# ── Super-title ───────────────────────────────────────────────────────────────
status_text = fig.text(0.5, 0.955, "Waiting for data...",
                        ha="center", va="top", fontsize=12,
                        color="#dddddd", fontweight="bold")

plt.ion()
plt.show()

# ── Parsing ───────────────────────────────────────────────────────────────────

def parse_line(line):
    """Return (timestamp_ms, data_fields) or None on bad/comment lines."""
    if not line or line.startswith("#") or "timestamp" in line:
        return None
    parts = line.split(",")
    if len(parts) < 17:   # timestamp + 16 data fields
        return None
    try:
        ts   = int(parts[0])
        data = [float(p) for p in parts[1:]]
        return ts, data
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

        # Save previous values for frame delta
        prev_vals = dict(last_vals)

        for idx, *_ in CHANNELS:
            last_vals[idx] = data[idx]
            history[idx].append(data[idx])
        last_R   = data[IDX_R]
        last_G   = data[IDX_G]
        last_B   = data[IDX_B]
        last_VIS = data[IDX_VIS]
        ts_history.append(ts / 1000.0)

        # Bar chart
        cur_vals = [last_vals[idx] for idx, *_ in CHANNELS]
        max_val  = max(max(cur_vals), 1)
        for bar, h in zip(bars_on, cur_vals):
            bar.set_height(h)
        ax_bar.set_ylim(0, max_val * 1.15)

        # Frame-to-frame delta
        diff_vals = [last_vals[idx] - prev_vals[idx] for idx, *_ in CHANNELS]
        max_diff  = max(max(abs(v) for v in diff_vals), 1)
        for bar, h in zip(bars_diff, diff_vals):
            bar.set_height(h)
        ax_diff.set_ylim(-max_diff * 1.2, max_diff * 1.2)

        # Trend lines
        for idx in TREND_INDICES:
            trend_lines[idx].set_ydata(list(history[idx]))
        trend_max = max(
            (max(history[idx]) for idx in TREND_INDICES if max(history[idx]) > 0),
            default=1
        )
        ax_trend.set_ylim(0, trend_max * 1.15)

        # RGB swatch
        denom = max(last_R, last_G, last_B, 1.0)
        nr, ng, nb = last_R / denom, last_G / denom, last_B / denom
        swatch.set_facecolor((nr, ng, nb))
        rgb_text.set_text(f"R={last_R:.0f}  G={last_G:.0f}  B={last_B:.0f}")
        vis_text.set_text(f"VIS clear = {last_VIS:.0f}")

        # Status bar
        frame_count += 1
        elapsed = time.time() - t_start
        fps     = frame_count / elapsed if elapsed > 0 else 0
        status_text.set_text(
            f"t = {ts / 1000:.1f} s   "
            f"Peak = {max_val:.0f}   "
            f"Frame {frame_count}  ({fps:.1f} fps)"
        )

        fig.canvas.draw()
        fig.canvas.flush_events()

except KeyboardInterrupt:
    print("\nStopped by user.")
finally:
    ser.close()
    print("Serial port closed.")