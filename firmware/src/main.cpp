// Custom "AirTag" — GPS + LTE-M tracker firmware for LILYGO T-SIM7000G.
//
// Cycle: wake → power modem → GPS fix (with timeout) → LTE-M attach →
// HTTP POST one JSON ping to the self-hosted dashboard → modem off →
// ESP32 deep sleep. Everything is off between reports; deep-sleep draw
// on this board is ~1-2 mA (the modem's quiescent circuits dominate).

#include <Arduino.h>
#include "config.h"

#include <TinyGsmClient.h>
#include <ArduinoHttpClient.h>
#include <ArduinoJson.h>

// T-SIM7000G pin map (LilyGO schematic / official examples)
#define MODEM_PWR_PIN 4
#define MODEM_TX_PIN  27  // ESP32 TX -> SIM7000 RX
#define MODEM_RX_PIN  26  // ESP32 RX <- SIM7000 TX
#define LED_PIN       12
#define BAT_ADC_PIN   35  // battery voltage through onboard 1:2 divider

#define SerialAT Serial1

TinyGsm modem(SerialAT);
TinyGsmClient netClient(modem);
HttpClient http(netClient, SERVER_HOST, SERVER_PORT);

RTC_DATA_ATTR uint32_t bootCount = 0;

// The board runs PWRKEY through a level shifter, so the "hold low ≥1 s"
// power-on pulse from the SIM7000 datasheet is inverted here.
static void modemPowerOn() {
  pinMode(MODEM_PWR_PIN, OUTPUT);
  digitalWrite(MODEM_PWR_PIN, HIGH);
  delay(1200);
  digitalWrite(MODEM_PWR_PIN, LOW);
}

static uint16_t readBatteryMilliVolts() {
  analogSetAttenuation(ADC_11db);
  uint32_t sum = 0;
  for (int i = 0; i < 8; i++) {
    sum += analogReadMilliVolts(BAT_ADC_PIN);
    delay(2);
  }
  return (uint16_t)((sum / 8) * 2);  // undo the 1:2 divider
}

static void goToSleep() {
  // Cut GPS antenna power and shut the modem down before sleeping.
  modem.sendAT("+SGPIO=0,4,1,0");
  modem.waitResponse(1000L);
  modem.poweroff();
  digitalWrite(LED_PIN, HIGH);  // LED off (active low)
  Serial.printf("Sleeping %d min\n", SLEEP_MINUTES);
  Serial.flush();
  esp_sleep_enable_timer_wakeup((uint64_t)SLEEP_MINUTES * 60ULL * 1000000ULL);
  esp_deep_sleep_start();
}

struct Fix {
  bool  valid = false;
  float lat = 0, lon = 0, speed = 0, alt = 0;
  int   sats = 0;
};

static Fix acquireGps() {
  Fix fix;
  // SGPIO 4 switches the active GPS antenna's power rail on this board.
  modem.sendAT("+SGPIO=0,4,1,1");
  modem.waitResponse(1000L);
  modem.enableGPS();

  uint32_t deadline = millis() + GPS_TIMEOUT_S * 1000UL;
  while (millis() < deadline) {
    int vsat = 0, usat = 0;
    float accuracy = 0;
    if (modem.getGPS(&fix.lat, &fix.lon, &fix.speed, &fix.alt,
                     &vsat, &usat, &accuracy)) {
      fix.valid = true;
      fix.sats = usat;
      Serial.printf("Fix: %.6f,%.6f sats=%d\n", fix.lat, fix.lon, usat);
      break;
    }
    digitalWrite(LED_PIN, !digitalRead(LED_PIN));  // blink while searching
    delay(2000);
  }
  modem.disableGPS();
  return fix;
}

static bool sendPing(const Fix& fix, uint16_t battMv) {
  JsonDocument doc;
  doc["id"]      = DEVICE_ID;
  doc["fix"]     = fix.valid;
  if (fix.valid) {
    doc["lat"]   = fix.lat;
    doc["lon"]   = fix.lon;
    doc["speed"] = fix.speed;
    doc["alt"]   = fix.alt;
    doc["sats"]  = fix.sats;
  }
  doc["batt_mv"] = battMv;
  doc["boot"]    = bootCount;
  doc["csq"]     = modem.getSignalQuality();

  String body;
  serializeJson(doc, body);
  Serial.println("POST " + body);

  http.setTimeout(20000);
  http.beginRequest();
  http.post(SERVER_PATH);
  http.sendHeader("Content-Type", "application/json");
  http.sendHeader("X-Token", API_TOKEN);
  http.sendHeader("Content-Length", body.length());
  http.beginBody();
  http.print(body);
  http.endRequest();

  int status = http.responseStatusCode();
  http.responseBody();  // drain
  http.stop();
  Serial.printf("HTTP %d\n", status);
  return status >= 200 && status < 300;
}

void setup() {
  bootCount++;
  Serial.begin(115200);
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);  // LED on = awake

  uint16_t battMv = readBatteryMilliVolts();
  Serial.printf("Boot %u, batt %u mV\n", bootCount, battMv);

  modemPowerOn();
  SerialAT.begin(115200, SERIAL_8N1, MODEM_RX_PIN, MODEM_TX_PIN);

  // The modem takes a few seconds to boot; poll AT until it answers.
  bool up = false;
  for (int i = 0; i < 15 && !up; i++) up = modem.testAT(1000);
  if (!up) {
    Serial.println("Modem not responding");
    goToSleep();
  }
  modem.init();

  // GPS first, radio second: SIM7000 shares the RF front end, and a
  // simultaneous LTE attach slows the GNSS cold start noticeably.
  Fix fix = acquireGps();

  modem.setNetworkMode(38);   // LTE only
  modem.setPreferredMode(1);  // CAT-M
  if (!modem.waitForNetwork(NET_TIMEOUT_S * 1000L) ||
      !modem.gprsConnect(GPRS_APN, GPRS_USER, GPRS_PASS)) {
    Serial.println("No network — will retry next wake");
    goToSleep();
  }
  Serial.println("Network up, IP: " + modem.getLocalIP());

  for (int attempt = 0; attempt < 3; attempt++) {
    if (sendPing(fix, battMv)) break;
    delay(3000);
  }

  modem.gprsDisconnect();
  goToSleep();
}

void loop() {}  // never reached — setup() ends in deep sleep
