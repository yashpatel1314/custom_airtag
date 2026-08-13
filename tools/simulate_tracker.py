"""Fake tracker: POSTs pings exactly like the firmware does, so you can test
the whole server + dashboard before the hardware arrives.

Usage: python simulate_tracker.py [server_url] [device_id]
       python simulate_tracker.py http://127.0.0.1:8000 tag-01
"""

import json
import math
import sys
import time
import urllib.request

SERVER = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
DEVICE = sys.argv[2] if len(sys.argv) > 2 else "tag-01"
TOKEN = "change-me-long-random-string"

# Wander in a loop around a start point, like a tag riding in a car.
LAT0, LON0 = 37.7749, -122.4194
batt_mv = 4150

for i in range(1000):
    angle = i * 0.15
    ping = {
        "id": DEVICE,
        "fix": i % 7 != 5,  # occasionally simulate a failed GPS fix
        "lat": LAT0 + 0.010 * math.sin(angle),
        "lon": LON0 + 0.014 * math.cos(angle),
        "speed": 25 + 10 * math.sin(i),
        "alt": 12.0,
        "sats": 7 + i % 4,
        "batt_mv": batt_mv,
        "csq": 18 + i % 6,
        "boot": i,
    }
    if not ping["fix"]:
        for k in ("lat", "lon", "speed", "alt", "sats"):
            ping.pop(k)
    req = urllib.request.Request(
        SERVER + "/api/ping",
        data=json.dumps(ping).encode(),
        headers={"Content-Type": "application/json", "X-Token": TOKEN},
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        print(f"ping {i}: HTTP {r.status} {r.read().decode()}")
    batt_mv -= 2
    time.sleep(float(sys.argv[3]) if len(sys.argv) > 3 else 2)
