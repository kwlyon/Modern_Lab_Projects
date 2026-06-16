#include "thingProperties.h"
#include <WiFiS3.h>

static bool printed = false;                 // print banner once
static unsigned long lastToggle = 0;
static const unsigned long BLINK_INTERVAL_MS = 500;
static bool ledState = LOW;

void setup() {
  Serial.begin(115200);
  while (!Serial) {}

  pinMode(LED_BUILTIN, OUTPUT);
  digitalWrite(LED_BUILTIN, LOW);

  // Initialize Cloud props, then start the IoT Cloud connection
  initProperties();
  ArduinoCloud.begin(ArduinoIoTPreferredConnection);

  setDebugMessageLevel(2);
  ArduinoCloud.printDebugInfo();
}

void loop() {
  ArduinoCloud.update();

  // Print your banner once Wi-Fi is up
  if (!printed && WiFi.status() == WL_CONNECTED) {
    Serial.print("Connecting to ");
    Serial.println(SECRET_SSID);  // uses your secret
    Serial.println();
    Serial.println(u8"✅ Connected (open/MAC registered)");
    Serial.print("IP Address: ");
    Serial.println(WiFi.localIP());
    printed = true;
  }

  // Blink when Cloud variable 'blink' is true
  if (blink) {
    unsigned long now = millis();
    if (now - lastToggle >= BLINK_INTERVAL_MS) {
      ledState = !ledState;
      digitalWrite(LED_BUILTIN, ledState);
      lastToggle = now;
    }
  } else {
    if (ledState != LOW) {
      ledState = LOW;
      digitalWrite(LED_BUILTIN, LOW);
    }
  }
}

// Called automatically whenever the Cloud 'blink' variable changes
void onBlinkChange() {
  Serial.print("Blink set to: ");
  Serial.println(blink ? "ON" : "OFF");
}
