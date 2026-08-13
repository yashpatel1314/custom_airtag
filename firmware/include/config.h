#pragma once

// ---- Identity ----
#define DEVICE_ID       "tag-01"

// ---- Server (your self-hosted dashboard) ----
// Public hostname or IP where server/app.py is reachable from the internet.
// No scheme, no path — just the host. Port 80 if behind a reverse proxy,
// 8000 if you expose uvicorn directly.
#define SERVER_HOST     "tracker.example.com"
#define SERVER_PORT     8000
#define SERVER_PATH     "/api/ping"

// Shared secret — must match API_TOKEN on the server. Change it!
#define API_TOKEN       "change-me-long-random-string"

// ---- Cellular ----
// Hologram's APN. If you use a different IoT SIM, set its APN here.
#define GPRS_APN        "hologram"
#define GPRS_USER       ""
#define GPRS_PASS       ""

// ---- Duty cycle ----
// Minutes of deep sleep between location reports. Battery life scales
// almost linearly with this: 10 min ≈ days, 60 min ≈ weeks on 3000 mAh.
#define SLEEP_MINUTES   15

// Give up on GPS after this many seconds and report fix=false anyway
// (cold starts outdoors typically fix in 30-60 s; indoors may never fix).
#define GPS_TIMEOUT_S   120

// Give up on the cellular network after this many seconds.
#define NET_TIMEOUT_S   90
