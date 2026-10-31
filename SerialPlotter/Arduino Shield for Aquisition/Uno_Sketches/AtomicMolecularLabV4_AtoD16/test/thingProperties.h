#pragma once
#include <ArduinoIoTCloud.h>
#include <Arduino_ConnectionHandler.h>

// ---- Cloud variables ----
bool blink = false;              // toggled from dashboard

// ---- Wi-Fi Secrets ----
// Set these in the Cloud "Secrets" panel (no quotes here)
const char SSID[] = SECRET_SSID;            // should be "UARK Registered"
const char PASS[] = SECRET_OPTIONAL_PASS;   // leave empty for open network

// UNO R4 WiFi uses WiFiS3
WiFiConnectionHandler ArduinoIoTPreferredConnection(SSID, PASS);

// Forward declaration of the change callback
void onBlinkChange();

void initProperties() {
  ArduinoCloud.addProperty(
    blink,
    READWRITE,
    ON_CHANGE,
    onBlinkChange
  );

  // Optional: name your Thing
  // ArduinoCloud.setThingName("UNO R4 WiFi — Cloud Blink");
}
