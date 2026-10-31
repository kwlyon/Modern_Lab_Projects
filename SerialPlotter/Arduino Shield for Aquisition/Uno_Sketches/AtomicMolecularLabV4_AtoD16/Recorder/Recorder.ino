// Single-input controller (cleaned)
// - Uses Adafruit ADS1115 library (GAIN_TWO, addr 0x49) exactly like your test sketch
// - 1x -> ADS channel 0
// - 10x -> ADS channel 2
// - Keeps SoftwareSerial passthrough and EEPROM scale factor for this one input

#include <SoftwareSerial.h>
#include <EEPROM.h>
#include <Wire.h>
#include <Adafruit_ADS1X15.h>

// ======= Pin & Serial Config =======
const uint32_t HW_BAUD = 115200;
const uint32_t SW_BAUD = 9600;

// SoftwareSerial uses (RX, TX)
const uint8_t SW_RX_PIN = A0;  // from external device -> Arduino
const uint8_t SW_TX_PIN = A1;  // from Arduino -> external device

// ======= Termination Characters =======
const char HW_TERM_CHAR = '\n';  // hardware serial line ending
const char SW_TERM_CHAR = '\n';  // software serial line ending

// ======= Identification =======
const char* DEVICE_NAME = "Modern Lab Data Acquisition Shield";

// ======= Acquisition Settings (single input only) =======
uint32_t acquisitionDelay = 100;   // ms between measurements
uint16_t samplesToAverage = 1;     // >=1
// Gain selection via channel choice (fixed mapping)
// 1x  -> ADS AIN0
// 10x -> ADS AIN2
uint8_t  channelSel       = 0;     // 0 = 1x (AIN0), 1 = 10x (AIN2)

// Running flag
bool isRunning = false;

// Common timing ticker
uint32_t lastSampleMs = 0;

// ======= Scaling (EEPROM stored) =======
const double   PREC_REF     = 1.8;     // Precision voltage source MCP1501T-18E/CHY
double         scaleFactor  = 1.0;     // Single input scale factor

// EEPROM layout
const int      SCALE_ADDR   = 0;

SoftwareSerial swSer(SW_RX_PIN, SW_TX_PIN);

// ======= Input Buffer =======
String buffer;                 // collects chars from Hardware Serial
const size_t MAX_BUF = 256;    // guard against runaway input

// ======= ADS1115 (Adafruit lib) =======
Adafruit_ADS1115 ads;  // 16-bit version
// Library settings to match your test sketch:
//   ads.setGain(GAIN_TWO);  // ±2.048 V
//   ads.begin(0x49);        // ADDR tied HIGH

// For “half-range = 0” math
const double ADS_FSR_VOLTS = 2.048;  // with GAIN_TWO the lib maps codes to 0..2.048 V

// ======= Forward Declarations =======
void serviceSerial();
bool parse(const String& line);
void maybeStreamSample();

double readAveragedADC(uint8_t channel, uint16_t n, double scaleFactor);

void loadScaleFromEEPROM();
void saveScaleToEEPROM(double val, int addr);

void startInput();
void stopAll();
void printIdn();

// ======= Setup / Loop =======
void setup() {
  Serial.begin(HW_BAUD);
  swSer.begin(SW_BAUD);
  // Wire.begin(); // Adafruit lib will init I2C as needed; harmless to call too.
  Serial.println(DEVICE_NAME);

  // Match the test sketch exactly
  if (!ads.begin(0x49)) {
    Serial.println("Failed to initialize ADS.");
    while (1) { delay(10); }
  }
  ads.setGain(GAIN_TWO); // ±2.048 V range

  analogReference(EXTERNAL);  // legacy (harmless if unused elsewhere)
  loadScaleFromEEPROM();
}

void loop() {
  serviceSerial();     // always service I/O both ways
  maybeStreamSample(); // emit data if running and delay elapsed
}

// ======= Serial Service =======
void serviceSerial() {
  // --- From Hardware Serial (USB) ---
  while (Serial.available() > 0) {
    char c = static_cast<char>(Serial.read());

    if (c == '\r' && HW_TERM_CHAR == '\n') continue; // normalize CRLF if using '\n'

    if (buffer.length() < MAX_BUF) buffer += c;

    if (c == HW_TERM_CHAR) {
      String line = buffer;
      line.trim();  // strip terminators + spaces

      bool handled = parse(line);

      if (!handled) {
        // Forward original content to SW
        swSer.print(line);
        swSer.print(SW_TERM_CHAR);
      }

      buffer = ""; // reset for next command
    }
  }

  // --- From Software Serial (immediate pass-through to HW) ---
  while (swSer.available() > 0) {
    int b = swSer.read();
    if (b >= 0) {
      Serial.write((uint8_t)b);
    }
  }
}

// ======= Streaming (single input) =======
// Emits "millis(),value<HW_TERM_CHAR>" at the requested cadence while running
void maybeStreamSample() {
  if (!isRunning) return;
  uint32_t now = millis();

  if (now - lastSampleMs >= acquisitionDelay) {
    double value = readAveragedADC(channelSel, samplesToAverage, scaleFactor);
    Serial.print(now);
    Serial.print(',');
    Serial.print(value, 6); // send double with precision
    Serial.print(HW_TERM_CHAR);
    lastSampleMs = now;
  }
}

// ======= Command Parser (single input) =======
// - "run"          -> start streaming, reply "#run"
// - "delay,<ms>"   -> set acquisitionDelay (>0), reply "#delay<ms>"
// - "avg,<n>"      -> set samplesToAverage (>=1), reply "#avg<n>"
// - "1x"           -> select AIN0 (1x), reply "#1x"
// - "10x"          -> select AIN2 (10x), reply "#10x"
// - "scale,<val>"  -> set scale factor, save to EEPROM, reply "#scale<val>"
// - "sf"           -> print scale factor
// - "stop"         -> stop streaming, reply "#stop"
// - "idn?"         -> print device name and command list
bool parse(const String& line) {
  // ----- Common -----
  if (line.equalsIgnoreCase("idn?")) {
    printIdn();
    return true;
  }

  if (line.equalsIgnoreCase("stop")) {
    stopAll();
    Serial.print(F("#stop"));
    Serial.print(HW_TERM_CHAR);
    return true;
  }

  if (line.equalsIgnoreCase("run")) {
    startInput();
    Serial.print(F("#run"));
    Serial.print(HW_TERM_CHAR);
    return true;
  }

  if (line.startsWith("delay,")) {
    String valStr = line.substring(6);
    valStr.trim();
    long newDelay = valStr.toInt();
    if (newDelay > 0) {
      acquisitionDelay = (uint32_t)newDelay;
      Serial.print(F("#delay"));
      Serial.print(acquisitionDelay);
      Serial.print(HW_TERM_CHAR);
      return true;
    }
    return false; // invalid -> forward to SW
  }

  if (line.startsWith("avg,")) {
    String valStr = line.substring(4);
    valStr.trim();
    long n = valStr.toInt();
    if (n >= 1) {
      samplesToAverage = (uint16_t)n;
      Serial.print(F("#avg"));
      Serial.print(samplesToAverage);
      Serial.print(HW_TERM_CHAR);
      return true;
    }
    return false; // invalid -> forward to SW
  }

  if (line.equalsIgnoreCase("1x")) {
    channelSel = 0; // ADS AIN0
    Serial.print(F("#1x"));
    Serial.print(HW_TERM_CHAR);
    return true;
  }

  if (line.equalsIgnoreCase("10x")) {
    channelSel = 1; // ADS AIN2
    Serial.print(F("#10x"));
    Serial.print(HW_TERM_CHAR);
    return true;
  }

  if (line.startsWith("scale,")) {
    String valStr = line.substring(6);
    valStr.trim();
    double newScale = atof(valStr.c_str());
    if (newScale > 0.0) {
      saveScaleToEEPROM(newScale, SCALE_ADDR);
      scaleFactor = newScale;
      Serial.print(F("#scale"));
      Serial.print(scaleFactor, 6);
      Serial.print(HW_TERM_CHAR);
      return true;
    }
    return false; // invalid
  }

  if (line.equalsIgnoreCase("sf")) {
    Serial.print("Scale: ");
    Serial.println(scaleFactor, 6);
    return true;
  }

  return false; // unrecognized
}

// ======= Start/Stop Helpers =======
void startInput() {
  isRunning = true;
  lastSampleMs = 0;
}

void stopAll() {
  isRunning = false;
}

// ======= EEPROM Helpers (single scale) =======
void loadScaleFromEEPROM() {
  double stored;
  EEPROM.get(SCALE_ADDR, stored);
  if (isnan(stored) || stored == 0.0) {
    stored = PREC_REF / (double)1024; // default: 1.8 V / 1024
    EEPROM.put(SCALE_ADDR, stored);
  }
  scaleFactor = stored;
}

void saveScaleToEEPROM(double val, int addr) {
  double current;
  EEPROM.get(addr, current);
  if (current != val) {
    EEPROM.put(addr, val);
  }
}

// ======= ADC Averaging (half-range = 0; Adafruit lib) =======
double readAveragedADC(uint8_t channel, uint16_t n, double scaleFactor) {
  if (n < 1) n = 1;

  double accum_counts_equiv = 0.0;

  for (uint16_t i = 0; i < n; ++i) {
    // Read single-ended volts from the selected channel (0..2.048 V with GAIN_TWO)
    int16_t raw = ads.readADC_SingleEnded(channel);
    double volts = ads.computeVolts(raw);
    double miliVolts = volts*1000;

    accum_counts_equiv  += miliVolts;
  }

  double avg_counts_equiv = accum_counts_equiv / (double)n;
  return avg_counts_equiv * scaleFactor;
}

// ======= IDN Printer =======
void printIdn() {
  Serial.println(DEVICE_NAME);
  Serial.println("Commands:");
  Serial.println("  run                 -> start stream");
  Serial.println("  delay,<ms>          -> set delay (ms>0)");
  Serial.println("  avg,<n>             -> set averages (n>=1)");
  Serial.println("  1x                  -> select AIN0 (1x)");
  Serial.println("  10x                 -> select AIN2 (10x)");
  Serial.println("  scale,<val>         -> set scale factor (persist)");
  Serial.println("  sf                  -> print scale factor");
  Serial.println("  stop                -> stop stream");
  Serial.println("  idn?                -> print this list");
}
