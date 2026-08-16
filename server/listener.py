"""BLE listener that runs on the server machine itself (Windows PC or
Raspberry Pi) — no ESP32 needed for the zone where the server lives.

Scans for Find My-format beacons and posts sightings to the tracker server,
exactly like the ESP32 listener firmware does.

Usage:
  python listener.py                          # defaults: home @ localhost
  python listener.py --listener garage --server http://192.168.1.3:8000
"""

import argparse
import asyncio
import json
import time
import urllib.request

from bleak import BleakScanner

APPLE_ID = 0x004C  # manufacturer data company id


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--server", default="http://127.0.0.1:8000")
    p.add_argument("--token", default="change-me-long-random-string")
    p.add_argument("--listener", default="home")
    p.add_argument("--lat", type=float, default=None)
    p.add_argument("--lon", type=float, default=None)
    p.add_argument("--interval", type=int, default=15,
                   help="seconds per scan/report cycle")
    return p.parse_args()


async def main():
    args = parse_args()
    mode = "FIND" if args.interval <= 3 else "watch"
    print(f"listener '{args.listener}' [{mode}] -> {args.server} "
          f"every {args.interval}s (ctrl+c to stop)")

    # Scanner runs continuously; we keep the latest RSSI + timestamp per MAC
    # and report on a timer. A tag counts as "still here" if seen within the
    # staleness window, so a fast Find-mode interval never drops a live tag
    # just because it didn't advertise in the last 1.5 s.
    recent = {}  # mac -> [rssi, monotonic_last_seen, batt_level]
    keep = max(6.0, args.interval * 2)

    # Find My status byte (payload[2]) encodes battery in its top bits.
    BATT = {0x10: "full", 0x40: "medium", 0x80: "low", 0xC0: "critical"}

    def on_advert(device, adv):
        payload = adv.manufacturer_data.get(APPLE_ID)
        # Find My offline-finding frame: type 0x12, length 0x19
        if payload and len(payload) >= 2 and payload[0] == 0x12 and payload[1] == 0x19:
            batt = BATT.get(payload[2] & 0xF0) if len(payload) >= 3 else None
            recent[device.address.upper()] = [adv.rssi or -100, time.monotonic(), batt]

    scanner = BleakScanner(detection_callback=on_advert)
    await scanner.start()
    try:
        while True:
            await asyncio.sleep(args.interval)
            now = time.monotonic()
            heard = {m: v for m, v in recent.items() if now - v[1] <= keep}
            for m in [m for m, v in recent.items() if now - v[1] > keep]:
                del recent[m]
            if not heard:
                print(time.strftime("%H:%M:%S"), "no beacons")
                continue
            body = {
                "listener": args.listener,
                "tags": [{"mac": m, "rssi": v[0], "batt": v[2]}
                         for m, v in heard.items()],
            }
            if args.lat is not None and args.lon is not None:
                body["lat"], body["lon"] = args.lat, args.lon
            req = urllib.request.Request(
                args.server + "/api/sighting",
                data=json.dumps(body).encode(),
                headers={"Content-Type": "application/json",
                         "X-Token": args.token},
            )
            try:
                with urllib.request.urlopen(req, timeout=10) as r:
                    resp = json.loads(r.read())
                rec = resp.get("recognized") or []
                print(time.strftime("%H:%M:%S"),
                      f"heard {len(heard)}, ours: {rec or 'none'}")
            except Exception as e:
                print(time.strftime("%H:%M:%S"), "post failed:", e)
    finally:
        await scanner.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
