---
name: flashing-a-listener-node
description: Use when setting up, configuring, or reflashing an ESP32 listener node for a new zone (home, garage, office, car), or when a zone stops reporting sightings.
---

# Flashing an ESP32 listener node

One classic ESP32 devkit per zone. Firmware lives in `firmware-listener/`
(PlatformIO, Arduino framework).

```bash
cd firmware-listener
cp include/config.h.example include/config.h   # first time only
# edit config.h: LISTENER_ID (zone name), WIFI_SSID/PASS,
#   SERVER_URL (PC's LAN IP from ipconfig, keep /api/sighting),
#   API_TOKEN (must match server/start-server.bat)
pio run -t upload          # board plugged in over USB
pio device monitor         # watch: WiFi connect -> "posted N tags"
```

## Constraints

- `config.h` is a gitignored secret (WiFi credentials) — never commit it.
- Classic ESP32 only; C3/S3 variants are untested with this firmware.
- Map pin for the zone: either uncomment `LISTENER_LAT/LON` in config.h,
  or add the zone to `server/landmarks.json` (server-side, no reflash —
  preferred). Without either, tags show zone-only presence ("at garage"),
  which is fine for e.g. a car node on USB power.
- Verify from the server side: the zone name appears as `listener` in
  `curl -s http://127.0.0.1:8000/api/devices` once it hears a tag.
