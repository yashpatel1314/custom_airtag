// BLE listener node: hears Find My-format beacons (our XIAO tags) and posts
// sightings to the tracker server. The server's tags.json decides which MACs
// are ours — neighbors' AirTags rotate their MACs and are simply ignored
// server-side, so adding a new tag never requires reflashing listeners.

#include <Arduino.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <NimBLEDevice.h>
#include <ArduinoJson.h>
#include "config.h"

#define LED_PIN 2  // onboard LED on most ESP32 devkits

struct Heard {
  String mac;
  int rssi;
};

// Find My advertisement: manufacturer data 4C 00 (Apple) 12 19 (offline finding).
static bool isFindMyAdvert(const NimBLEAdvertisedDevice* d) {
  const std::string& m = d->getManufacturerData();
  return m.size() >= 4 && (uint8_t)m[0] == 0x4C && (uint8_t)m[1] == 0x00 &&
         (uint8_t)m[2] == 0x12 && (uint8_t)m[3] == 0x19;
}

static void connectWifi() {
  if (WiFi.status() == WL_CONNECTED) return;
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  Serial.print("WiFi");
  for (int i = 0; i < 40 && WiFi.status() != WL_CONNECTED; i++) {
    delay(500);
    Serial.print(".");
  }
  Serial.println(WiFi.status() == WL_CONNECTED
                     ? " connected: " + WiFi.localIP().toString()
                     : " FAILED (will retry next cycle)");
}

void setup() {
  Serial.begin(115200);
  pinMode(LED_PIN, OUTPUT);
  connectWifi();
  NimBLEDevice::init("");
  NimBLEScan* scan = NimBLEDevice::getScan();
  scan->setActiveScan(false);  // passive is enough for adverts, uses less power
  scan->setInterval(100);
  scan->setWindow(99);
  Serial.printf("Listener '%s' up\n", LISTENER_ID);
}

void loop() {
  uint32_t cycleStart = millis();

  NimBLEScan* scan = NimBLEDevice::getScan();
  NimBLEScanResults results = scan->getResults(SCAN_SECONDS * 1000, false);

  // Keep the strongest RSSI per MAC seen during the window.
  std::vector<Heard> heard;
  for (int i = 0; i < results.getCount(); i++) {
    const NimBLEAdvertisedDevice* d = results.getDevice(i);
    if (!isFindMyAdvert(d)) continue;
    String mac = d->getAddress().toString().c_str();
    mac.toUpperCase();
    bool merged = false;
    for (auto& h : heard) {
      if (h.mac == mac) {
        h.rssi = max(h.rssi, (int)d->getRSSI());
        merged = true;
        break;
      }
    }
    if (!merged && heard.size() < 16) heard.push_back({mac, d->getRSSI()});
  }
  scan->clearResults();

  if (!heard.empty()) {
    connectWifi();
    if (WiFi.status() == WL_CONNECTED) {
      JsonDocument doc;
      doc["listener"] = LISTENER_ID;
#if defined(LISTENER_LAT) && defined(LISTENER_LON)
      doc["lat"] = LISTENER_LAT;
      doc["lon"] = LISTENER_LON;
#endif
      JsonArray tags = doc["tags"].to<JsonArray>();
      for (auto& h : heard) {
        JsonObject t = tags.add<JsonObject>();
        t["mac"] = h.mac;
        t["rssi"] = h.rssi;
      }
      String body;
      serializeJson(doc, body);

      HTTPClient http;
      http.begin(SERVER_URL);
      http.addHeader("Content-Type", "application/json");
      http.addHeader("X-Token", API_TOKEN);
      int status = http.POST(body);
      http.end();
      Serial.printf("heard %d beacon(s) -> HTTP %d\n", heard.size(), status);
      if (status == 200) {  // quick blink = report delivered
        digitalWrite(LED_PIN, HIGH);
        delay(80);
        digitalWrite(LED_PIN, LOW);
      }
    }
  } else {
    Serial.println("no beacons this cycle");
  }

  uint32_t elapsed = millis() - cycleStart;
  if (elapsed < CYCLE_SECONDS * 1000UL) delay(CYCLE_SECONDS * 1000UL - elapsed);
}
