---
name: verifying-a-tag
description: Use when checking whether a tag chip is alive and broadcasting, reading its battery level, or debugging a tag that does not appear on the dashboard or in listener output.
---

# Verifying a tag over BLE

Fastest ground truth, no server needed:

```bash
python tools/scan_tags.py        # 30 s scan; exit 0 iff a registered tag heard
```

Needs `bleak` installed and Bluetooth ON
(`powershell -File tools\enable-bluetooth.ps1`).

## Reading the output

```
C6:8C:B5:57:0E:16  rssi -59  adverts 3  batt full / 87%  -> REGISTERED as 'keyring'
```

- **Low advert counts are normal**: tags transmit every 1.3 s but Windows
  batches duplicates — a handful per 30 s scan means healthy.
- `batt full / n/a (stock/old fw)`: 4-level status works but the tag runs
  stock go-haystack or a pre-percentage build — reflash per
  `docs/adding-a-tag.md` §2 to get precise %.
- `-> not in tags.json`: either a stranger's Apple device (common,
  rotating MACs) or an unregistered tag — derive its expected MAC with
  `python tools/mac_from_key.py findmy/keys/<tag>.keys` and compare.
- Nothing heard at all: Bluetooth off, or tag unpowered/unflashed.

## Battery ground truth

The tag prints `batt mv <mV> pct <p>` on USB serial for ~16 s after boot
(then every 2 min). Calibration constants live in `firmware-tag/mcu.go`.
