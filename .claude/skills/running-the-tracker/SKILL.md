---
name: running-the-tracker
description: Use when asked to run, start, restart, or smoke-test the tracker server, dashboard, or BLE listener on this machine, or when the dashboard shows no data or a tag is missing from it.
---

# Running the tracker (server + PC listener)

Two processes, launched from `server/`: the FastAPI server (dashboard +
API + SQLite) and the PC's own BLE listener. Their tokens must match.

## Launch (normal path)

```
server\start-server.bat      # window 1 — sets API_TOKEN, runs uvicorn :8000
server\start-listener.bat    # window 2 — BLE scan -> POST /api/sighting
```

Both `.bat` files are gitignored secrets. If missing (fresh clone), copy
from the `.example` versions and paste the same random token into both.

## Preconditions (each has bitten before)

- `pip install fastapi uvicorn bleak` — fresh machines lack all three.
- **Bluetooth radio ON** or the listener dies with
  `BleakBluetoothNotAvailableError: Bluetooth radio is not powered on` —
  fix from a shell with `powershell -File tools\enable-bluetooth.ps1`.
- Tag must be registered in `server/tags.json` (server reads it at
  startup — restart after editing).

## Verify it's actually working

```bash
curl -s http://127.0.0.1:8000/api/devices
```

A live tag appears within ~15 s (one listener cycle) with its `listener`
zone, `rssi`, and `batt_lvl`. Empty `[]` = listener not posting or tag not
heard — run `python tools/scan_tags.py` to split those two cases.

Manual launch (e.g. throwaway token for testing):
`API_TOKEN=x python -m uvicorn app:app --port 8000` in `server/`, then
`python listener.py --token x`.

`fix: 0` with null lat/lon is normal for a listener with no coordinates —
zone-only presence. Map pins need `server/landmarks.json` (copy from
example) or `--lat/--lon` on the listener.
