"""Verify tags are alive: scan BLE for Find My-format beacons and report which
registered tags (server/tags.json) are heard, with signal and battery.

Usage:
  python tools/scan_tags.py            # 30s scan
  python tools/scan_tags.py 10         # custom duration in seconds

Exit code 0 if at least one registered tag was heard, 1 otherwise.
Requires: pip install bleak, and the PC's Bluetooth radio ON
(tools/enable-bluetooth.ps1 turns it on from a shell).
"""

import asyncio
import json
import sys
import time
from pathlib import Path

from bleak import BleakScanner

APPLE_ID = 0x004C
# Find My status byte (payload[2]) battery bits — same map as server/listener.py
BATT = {0x10: "full", 0x40: "medium", 0x80: "low", 0xC0: "critical"}

TAGS_PATH = Path(__file__).resolve().parents[1] / "server" / "tags.json"
TAGS = {k.upper(): v for k, v in json.loads(TAGS_PATH.read_text()).items()}

DURATION = int(sys.argv[1]) if len(sys.argv) > 1 else 30
seen = {}  # mac -> latest decoded advert


def on_advert(device, adv):
    payload = adv.manufacturer_data.get(APPLE_ID)
    # Find My offline-finding frame: type 0x12, length 0x19
    if payload and len(payload) >= 2 and payload[0] == 0x12 and payload[1] == 0x19:
        mac = device.address.upper()
        e = seen.setdefault(mac, {"count": 0})
        e["count"] += 1
        e["rssi"] = adv.rssi
        e["status"] = payload[2]
        e["batt_lvl"] = BATT.get(payload[2] & 0xF0)
        # Our firmware's precise 0-100% in the trailing hint byte; stock
        # firmware leaves it 0x00 ("unknown"), foreign Apple devices put
        # other data there — only 1..100 is a real reading.
        pct = payload[26] if len(payload) >= 27 else 0
        e["batt_pct"] = pct if 0 < pct <= 100 else None


async def main():
    scanner = BleakScanner(detection_callback=on_advert)
    await scanner.start()
    print(f"scanning {DURATION}s for Find My beacons...")
    await asyncio.sleep(DURATION)
    await scanner.stop()

    if not seen:
        print("RESULT: no Find My beacons heard at all")
        return 1
    print(f"\nheard {len(seen)} Find My beacon(s):")
    for mac, e in sorted(seen.items()):
        name = TAGS.get(mac)
        tagstr = f"REGISTERED as '{name}'" if name else "not in tags.json"
        pct = f"{e['batt_pct']}%" if e["batt_pct"] is not None else "n/a (stock/old fw)"
        print(f"  {mac}  rssi {e['rssi']:4d}  adverts {e['count']:3d}  "
              f"batt {e['batt_lvl']} / {pct}  -> {tagstr}")
    ours = [TAGS[m] for m in seen if m in TAGS]
    print(f"\nRESULT: registered tags heard: {ours or 'NONE'}")
    return 0 if ours else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
