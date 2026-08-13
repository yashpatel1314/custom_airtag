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
    print(f"listener '{args.listener}' -> {args.server} (ctrl+c to stop)")
    while True:
        heard = {}  # mac -> best rssi

        def on_advert(device, adv):
            payload = adv.manufacturer_data.get(APPLE_ID)
            # Find My offline-finding frame: type 0x12, length 0x19
            if payload and len(payload) >= 2 and payload[0] == 0x12 and payload[1] == 0x19:
                mac = device.address.upper()
                rssi = adv.rssi or -100
                heard[mac] = max(heard.get(mac, -999), rssi)

        scanner = BleakScanner(detection_callback=on_advert)
        await scanner.start()
        await asyncio.sleep(max(5, args.interval - 2))
        await scanner.stop()

        if heard:
            body = {
                "listener": args.listener,
                "tags": [{"mac": m, "rssi": r} for m, r in heard.items()],
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
                print(time.strftime("%H:%M:%S"),
                      f"heard {len(heard)} beacon(s), recognized: "
                      f"{resp.get('recognized') or 'none'}")
            except Exception as e:
                print(time.strftime("%H:%M:%S"), "post failed:", e)
        else:
            print(time.strftime("%H:%M:%S"), "no beacons this cycle")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
