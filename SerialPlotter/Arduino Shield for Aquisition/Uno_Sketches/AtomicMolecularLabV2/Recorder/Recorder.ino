//This shit was definitely "vibe coded"
#include <SoftwareSerial.h>
#include <EEPROM.h>

// ======= Pin & Serial Config =======
const uint32_t HW_BAUD = 115200;
const uint32_t SW_BAUD = 9600;

// SoftwareSerial uses (RX, TX)
const uint8_t SW_RX_PIN = A0;  // from external device -> Arduino
const uint8_t SW_TX_PIN = A1;  // from Arduino -> external device

// ======= Termination Characters =======
const char HW_TERM_CHAR = '\n';  // hardware serial line ending
const char SW_TERM_CHAR = '\n';  // software serial line ending

// ======= Acquisition Settings =======
uint8_t        analogReadPin    = A2;   // A/D input pin (default A2)
uint32_t       acquisitionDelay = 100;  // ms between measurements (default)
uint16_t       samplesToAverage = 1;    // consecutive ADC reads to average (>=1)
bool           isRunning        = false;

// ======= Scaling (EEPROM stored) =======
double         scaleFactor      = 1.0;
const int      SCALE_ADDR       = 0;  // EEPROM address for scale

SoftwareSerial swSer(SW_RX_PIN, SW_TX_PIN);

// ======= Globals =======
String buffer;                 // collects chars from Hardware Serial
const size_t MAX_BUF = 256;    // guard against runaway input
uint32_t lastSampleMs = 0;     // ticker for non-blocking timing

// ======= Forward Declarations =======
void serviceSerial();
bool parse(const String& line);
void maybeStreamSample();
double readAveragedADC(uint8_t pin, uint16_t n);
void loadScaleFromEEPROM();
void saveScaleToEEPROM(double val);

void setup() {
  Serial.begin(HW_BAUD);
  swSer.begin(SW_BAUD);
  Serial.println("Modern Lab Data Acquisition Shield");

  loadScaleFromEEPROM();
}

void loop() {
  serviceSerial();     // always service I/O both ways
  maybeStreamSample(); // emit data if running and delay elapsed
}

// Handles data flow in both directions.
// - HW -> buffer; on termination char: parse(); if unrecognized, forward to SW; then clear buffer
// - SW -> immediately echo to HW (we never parse SW input)
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

// Average N consecutive ADC reads and return the scaled mean
double readAveragedADC(uint8_t pin, uint16_t n) {
  if (n < 1) n = 1;
  uint32_t sum = 0;
  for (uint16_t i = 0; i < n; ++i) {
    sum += (uint16_t)analogRead(pin);
  }
  double avg = (double)sum / (double)n;
  return avg * scaleFactor;  // apply correction
}

// Emits "millis(),ADC<HW_TERM_CHAR>" at the requested cadence while running
void maybeStreamSample() {
  if (!isRunning) return;

  uint32_t now = millis();
  if (now - lastSampleMs >= acquisitionDelay) {
    double value = readAveragedADC(analogReadPin, samplesToAverage);
    Serial.print(now);
    Serial.print(',');
    Serial.print(value, 6); // send double with precision
    Serial.print(HW_TERM_CHAR);
    lastSampleMs = now;
  }
}

// Minimal parser with compact acknowledgements.
// - "run"          -> start streaming, reply "#run"
// - "stop"         -> stop streaming, reply "#stop"
// - "delay,<ms>"   -> set acquisitionDelay (>0), reply "#delay<ms>"
// - "avg,<n>"      -> set samplesToAverage (>=1), reply "#avg<n>"
// - "1x"           -> set analogReadPin to A2, reply "#1x"
// - "10x"          -> set analogReadPin to A3, reply "#10x"
// - "scale,<val>"  -> set scale factor, save to EEPROM, reply "#scale<val>"
bool parse(const String& line) {
  if (line.equalsIgnoreCase("run")) {
    isRunning = true;
    lastSampleMs = 0;
    Serial.print(F("#run"));
    Serial.print(HW_TERM_CHAR);
    return true;

  } else if (line.equalsIgnoreCase("stop")) {
    isRunning = false;
    Serial.print(F("#stop"));
    Serial.print(HW_TERM_CHAR);
    return true;

  } else if (line.startsWith("delay,")) {
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

  } else if (line.startsWith("avg,")) {
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

  } else if (line.equalsIgnoreCase("1x")) {
    analogReadPin = A2;
    Serial.print(F("#1x"));
    Serial.print(HW_TERM_CHAR);
    return true;

  } else if (line.equalsIgnoreCase("10x")) {
    analogReadPin = A3;
    Serial.print(F("#10x"));
    Serial.print(HW_TERM_CHAR);
    return true;

  } else if (line.startsWith("scale,")) {
    String valStr = line.substring(6);
    valStr.trim();
    double newScale = valStr.toDouble();
    if (newScale > 0.0) {
      saveScaleToEEPROM(newScale);
      scaleFactor = newScale;
      Serial.print(F("#scale"));
      Serial.print(scaleFactor, 6);
      Serial.print(HW_TERM_CHAR);
      return true;
    }
    return false; // invalid
  }

  return false; // unrecognized
}

// ======= EEPROM Helpers =======
void loadScaleFromEEPROM() {
  double stored;
  EEPROM.get(SCALE_ADDR, stored);
  if (isnan(stored) || stored == 0.0) {
    stored = 1.0;
    EEPROM.put(SCALE_ADDR, stored);
  }
  scaleFactor = stored;
}

void saveScaleToEEPROM(double val) {
  double current;
  EEPROM.get(SCALE_ADDR, current);
  if (current != val) {
    EEPROM.put(SCALE_ADDR, val);
  }
}

