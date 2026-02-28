# VIS-NIR Spectral Sensor Test — AS7343 + ESP32

A test project to evaluate the functionality of the **AS7343 14/18-channel multi-spectral sensor** using a generic GY-AS7343 breakout board and an ESP32 dev board. Includes firmware (PlatformIO) and a real-time Python plotter.

---

## Hardware

| Component | Details |
|---|---|
| Sensor | AS7343 — GY-AS7343 (generic Chinese breakout, non-Qwiic) |
| Microcontroller | ESP32 Dev Board (38-pin / 34 GPIO) |
| Library | [Adafruit AS7343](https://github.com/adafruit/Adafruit_AS7343) |
| IDE | [PlatformIO](https://platformio.org/) |

> **Note:** The Adafruit library supports 18 channels (auto-SMUX mode). This particular GY-AS7343 board may only expose 14 physical channels — the remaining slots will read zero or near-zero.

---

## Wiring

| GY-AS7343 Pin | ESP32 Pin | Notes |
|---|---|---|
| VIN | 3.3V | **Do NOT use 5V — sensor is 3.3V only** |
| GND | GND | |
| SCL | GPIO 22 | I2C clock (default ESP32 I2C) |
| SDA | GPIO 21 | I2C data (default ESP32 I2C) |
| GAIN | 3.3V | Pull high to set I2C address 0x39 |
| INT | GPIO 23 | Interrupt (optional, not used in this sketch) |

---

## Spectral Channels

| Channel | Peak λ | Description |
|---|---|---|
| F1 | 405 nm | Violet |
| F2 | 425 nm | Violet-blue |
| FZ | 450 nm | Blue |
| F3 | 475 nm | Blue-cyan |
| F4 | 515 nm | Green |
| F5 | 550 nm | Green-yellow |
| FY | 555 nm | Yellow-green (wide) |
| FXL | 600 nm | Orange (wide) |
| F6 | 640 nm | Red |
| F7 | 690 nm | Deep red |
| F8 | 745 nm | Near-IR |
| NIR | 855 nm | Near-IR |
| VIS | broadband | Clear / visible |
| FD | broadband | Flicker detection |

---

## Project Structure

```
├── src/
│   └── main.cpp          # ESP32 firmware — continuous spectral logging over Serial
├── platformio.ini        # PlatformIO build config
└── live_plot.py          # Real-time Python visualiser (runs on PC)
```

---

## Firmware

### Configuration (top of `main.cpp`)

```cpp
static constexpr as7343_gain_t GAIN        = AS7343_GAIN_64X;  // adjust for lighting
static constexpr uint8_t       ATIME       = 29;               // integration time multiplier
static constexpr uint16_t      ASTEP       = 599;              // integration step size
static constexpr uint8_t       SAMPLES     = 3;                // readings averaged per line
static constexpr uint16_t      LED_CURRENT_MA = 50;            // onboard LED drive current
```

Integration time formula: `t_int = (ATIME + 1) × (ASTEP + 1) × 2.78 µs` ≈ **50 ms** at defaults.

### Build & Flash (PlatformIO)

```bash
pio run --target upload
pio device monitor --baud 115200
```

### Serial Output

CSV format, one line per measurement:

```
timestamp_ms, F1_405nm, F2_425nm, FZ_450nm, F3_475nm, F4_515nm, F5_550nm,
FY_555nm, FXL_600nm, F6_640nm, F7_690nm, F8_745nm, NIR_855nm,
VIS_clear, R_approx, G_approx, B_approx
```

Lines starting with `#` are comments and can be filtered out.

---

## Python Plotter

Real-time visualiser with four panels:
- **Live spectrum** — bar chart of all 12 spectral channels
- **Frame delta** — change since the last reading (useful for detecting movement)
- **Rolling trend** — last 60 readings for key channels
- **Colour swatch** — approximate object colour derived from R/G/B

### Requirements

```bash
pip install pyserial matplotlib
```

### Run

```bash
python live_plot.py          # defaults to COM5 (Windows) or /dev/ttyUSB0 (Linux/Mac)
python live_plot.py COM3
python live_plot.py /dev/ttyACM0
```

---

## Notes

- The LED stays **on continuously** — this is active illumination mode, not ambient measurement
- For repeatable cross-session results, consider measuring a white reference tile first and normalising readings against it
- Consistent measurement distance (~5 cm worked well in testing) and perpendicular orientation to the target matter more than the exact distance
- Reduce `GAIN` or lower `ATIME`/`ASTEP` if the serial monitor reports digital saturation warnings

---

## License

Test / experimental code — no warranty. Feel free to use and adapt.
