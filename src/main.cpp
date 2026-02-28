/*
 * AS7343 14-Channel Spectral Logger
 * For GY-AS734x breakout board (bare I2C, non-Qwiic)
 *
 * Wiring (GY-AS734x → ESP32):
 *   VCC  → 3.3V  (DO NOT use 5V — sensor is 3.3V only!)
 *   GND  → GND
 *   SDA  → GPIO 21
 *   SCL  → GPIO 22
 *   GAIN → 3.3V
 *   INT  → GPIO 23 (optional, not used here)
 *
 * Output: CSV over Serial at 115200 baud
 * Columns: timestamp_ms,
 *          F1(405), F2(425), FZ(450), F3(475), F4(515), F5(550),
 *          FY(555), FXL(600), F6(640), F7(690), F8(745), NIR(855),
 *          VIS_clear, R_approx, G_approx, B_approx
 *
 * LED stays ON continuously — no ambient subtraction.
 */

#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_AS7343.h>

// ── Configuration ─────────────────────────────────────────────────────────────

// Spectral gain — lower if channels saturate, higher if readings are too low
// Bright sunlight: GAIN_0_5X–GAIN_4X | Indoor ambient: GAIN_64X–GAIN_256X
static constexpr as7343_gain_t GAIN        = AS7343_GAIN_64X;

// Integration time: t_int = (ATIME+1) × (ASTEP+1) × 2.78 µs ≈ 50 ms default
static constexpr uint8_t  ATIME           = 29;   // 0–255
static constexpr uint16_t ASTEP           = 599;  // 0–65534

// Number of readings averaged per log line (reduces ADC noise)
static constexpr uint8_t  SAMPLES         = 3;

// LED drive current in mA (4–258, even values)
static constexpr uint16_t LED_CURRENT_MA  = 50;

// Extra delay between log lines in ms (0 = as fast as possible)
// Each line already takes roughly SAMPLES * integration_time (~150ms at defaults)
static constexpr uint32_t SAMPLE_DELAY_MS = 0UL;

// ── Globals ───────────────────────────────────────────────────────────────────

Adafruit_AS7343 sensor;

// ── Helpers ───────────────────────────────────────────────────────────────────

/**
 * Print a rounded average of a 32-bit accumulator as uint16, followed by
 * either a comma or newline.
 */
static void printAvg(uint32_t sum, uint8_t n, bool newline = false) {
  uint32_t avg = (sum + n / 2) / n;  // rounded integer division
  if (avg > 65535U) avg = 65535U;    // clamp to ADC range
  if (newline) {
    Serial.println(static_cast<uint16_t>(avg));
  } else {
    Serial.print(static_cast<uint16_t>(avg));
    Serial.print(',');
  }
}

/**
 * Acquire SAMPLES measurements, accumulate into 32-bit buffers, then emit
 * one CSV row. readAllChannels() handles measurement start/stop internally.
 */
static void logReading() {
  uint32_t acc[18] = {};
  uint8_t  goodSamples = 0;

  for (uint8_t s = 0; s < SAMPLES; s++) {
    uint16_t ch[18];
    if (!sensor.readAllChannels(ch)) {
      Serial.println(F("# WARNING: readAllChannels() failed — skipping sample"));
      delay(10);
      continue;
    }

    if (sensor.isDigitalSaturated()) {
      Serial.println(F("# WARNING: digital saturation — reduce gain or ATIME/ASTEP"));
    }

    for (uint8_t i = 0; i < 18; i++) {
      acc[i] += ch[i];
    }
    goodSamples++;
    delay(5);
  }

  if (goodSamples == 0) {
    Serial.println(F("# ERROR: no valid samples this interval"));
    return;
  }

  // ── Derived / combined channels ───────────────────────────────────────────

  // Broadband VIS: average of the 3 pairs of clear-channel readings
  uint32_t vis_avg = (
    acc[AS7343_CHANNEL_VIS_TL_0] + acc[AS7343_CHANNEL_VIS_BR_0] +
    acc[AS7343_CHANNEL_VIS_TL_1] + acc[AS7343_CHANNEL_VIS_BR_1] +
    acc[AS7343_CHANNEL_VIS_TL_2] + acc[AS7343_CHANNEL_VIS_BR_2]
  ) / 6;

  // Approximate RGB by spectral integration (not colorimetry):
  //   R ≈ FXL(600) + F6(640)
  //   G ≈ F4(515) + F5(550) + FY(555)
  //   B ≈ F1(405) + F2(425) + FZ(450) + F3(475)
  uint32_t R_acc = acc[AS7343_CHANNEL_FXL] + acc[AS7343_CHANNEL_F6];
  uint32_t G_acc = acc[AS7343_CHANNEL_F4]  + acc[AS7343_CHANNEL_F5] + acc[AS7343_CHANNEL_FY];
  uint32_t B_acc = acc[AS7343_CHANNEL_F1]  + acc[AS7343_CHANNEL_F2] +
                   acc[AS7343_CHANNEL_FZ]  + acc[AS7343_CHANNEL_F3];

  // ── CSV row ───────────────────────────────────────────────────────────────
  Serial.print(millis());
  Serial.print(',');

  // 12 spectral channels in wavelength order
  printAvg(acc[AS7343_CHANNEL_F1],  goodSamples);   // 405 nm
  printAvg(acc[AS7343_CHANNEL_F2],  goodSamples);   // 425 nm
  printAvg(acc[AS7343_CHANNEL_FZ],  goodSamples);   // 450 nm
  printAvg(acc[AS7343_CHANNEL_F3],  goodSamples);   // 475 nm
  printAvg(acc[AS7343_CHANNEL_F4],  goodSamples);   // 515 nm
  printAvg(acc[AS7343_CHANNEL_F5],  goodSamples);   // 550 nm
  printAvg(acc[AS7343_CHANNEL_FY],  goodSamples);   // 555 nm
  printAvg(acc[AS7343_CHANNEL_FXL], goodSamples);   // 600 nm
  printAvg(acc[AS7343_CHANNEL_F6],  goodSamples);   // 640 nm
  printAvg(acc[AS7343_CHANNEL_F7],  goodSamples);   // 690 nm
  printAvg(acc[AS7343_CHANNEL_F8],  goodSamples);   // 745 nm
  printAvg(acc[AS7343_CHANNEL_NIR], goodSamples);   // 855 nm

  // Broadband / derived (already divided above, pass n=1)
  printAvg(vis_avg, 1);                  // VIS clear
  printAvg(R_acc,   goodSamples);        // R approx
  printAvg(G_acc,   goodSamples);        // G approx
  printAvg(B_acc,   goodSamples, true);  // B approx — newline
}

// ── Setup ─────────────────────────────────────────────────────────────────────

void setup() {
  Serial.begin(115200);
  while (!Serial) delay(10);

  Serial.println(F("# AS7343 Spectral Logger — initialising"));

  if (!sensor.begin()) {
    Serial.println(F("# FATAL: sensor not found. Check SDA/SCL wiring and 3.3V supply."));
    while (true) delay(10);
  }

  Serial.print(F("# Part ID: 0x"));  Serial.println(sensor.getPartID(),     HEX);
  Serial.print(F("# Rev ID:  0x"));  Serial.println(sensor.getRevisionID(), HEX);
  Serial.print(F("# Aux ID:  0x"));  Serial.println(sensor.getAuxID(),      HEX);

  sensor.setGain(GAIN);
  sensor.setATIME(ATIME);
  sensor.setASTEP(ASTEP);
  sensor.setSMUXMode(AS7343_SMUX_18CH);

  sensor.setLEDCurrent(LED_CURRENT_MA);
  sensor.enableLED(true);  // stays on for the lifetime of the sketch

  Serial.print(F("# LED current: "));
  Serial.print(LED_CURRENT_MA);
  Serial.println(F(" mA"));

  Serial.print(F("# Integration time: "));
  Serial.print(sensor.getIntegrationTime(), 2);
  Serial.println(F(" ms"));

  // ── Channel presence check ────────────────────────────────────────────────
  // Runs once at startup — point the sensor at a light source.
  // Any channel stuck at 0 regardless of lighting is likely not
  // physically present on this board variant.
  Serial.println(F("# Channel check (point sensor at a light source):"));
  uint16_t ch[18];
  if (sensor.readAllChannels(ch)) {
    Serial.print(F("#   F1  405nm = ")); Serial.println(ch[AS7343_CHANNEL_F1]);
    Serial.print(F("#   F2  425nm = ")); Serial.println(ch[AS7343_CHANNEL_F2]);
    Serial.print(F("#   FZ  450nm = ")); Serial.println(ch[AS7343_CHANNEL_FZ]);
    Serial.print(F("#   F3  475nm = ")); Serial.println(ch[AS7343_CHANNEL_F3]);
    Serial.print(F("#   F4  515nm = ")); Serial.println(ch[AS7343_CHANNEL_F4]);
    Serial.print(F("#   F5  550nm = ")); Serial.println(ch[AS7343_CHANNEL_F5]);
    Serial.print(F("#   FY  555nm = ")); Serial.println(ch[AS7343_CHANNEL_FY]);
    Serial.print(F("#   FXL 600nm = ")); Serial.println(ch[AS7343_CHANNEL_FXL]);
    Serial.print(F("#   F6  640nm = ")); Serial.println(ch[AS7343_CHANNEL_F6]);
    Serial.print(F("#   F7  690nm = ")); Serial.println(ch[AS7343_CHANNEL_F7]);
    Serial.print(F("#   F8  745nm = ")); Serial.println(ch[AS7343_CHANNEL_F8]);
    Serial.print(F("#   NIR 855nm = ")); Serial.println(ch[AS7343_CHANNEL_NIR]);
    Serial.print(F("#   VIS_TL    = ")); Serial.println(ch[AS7343_CHANNEL_VIS_TL_0]);
    Serial.print(F("#   VIS_BR    = ")); Serial.println(ch[AS7343_CHANNEL_VIS_BR_0]);
  } else {
    Serial.println(F("# Channel check failed — sensor may not be ready"));
  }

  Serial.println(F("# Lines prefixed '#' are comments — safe to filter in your CSV parser."));
  Serial.println();

  // CSV header
  Serial.println(F("timestamp_ms,"
                   "F1_405nm,F2_425nm,FZ_450nm,F3_475nm,"
                   "F4_515nm,F5_550nm,FY_555nm,FXL_600nm,"
                   "F6_640nm,F7_690nm,F8_745nm,NIR_855nm,"
                   "VIS_clear,R_approx,G_approx,B_approx"));
}

// ── Loop ──────────────────────────────────────────────────────────────────────

void loop() {
  logReading();
  if (SAMPLE_DELAY_MS > 0) delay(SAMPLE_DELAY_MS);
}