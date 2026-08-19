# Adding another tag, start to finish

Every tag is a Seeed XIAO nRF52840 (~$10, 3-pack ~$28) + a 3.7 V LiPo
(~$5, 100–500 mAh). One tag = ~20 minutes the first time, ~5 after that.
This walkthrough takes a blank board to a named pin on the dashboard.

## 0. One-time toolchain (skip if already installed)

- **Go** ≥1.22 and **TinyGo** ≥0.31 with the nRF52840 target
  ([tinygo.org/getting-started](https://tinygo.org/getting-started/)).
- The **haystack** CLI and the **go-haystack** repo, which our battery
  firmware builds against:

```bash
go install github.com/hybridgroup/go-haystack/cmd/haystack@latest
git clone https://github.com/hybridgroup/go-haystack
```

## 1. Generate the tag's keypair

Every tag needs its own key — the key IS the tag's identity.

```bash
haystack keys tag-04     # writes tag-04.keys + tag-04.json
```

Move both files into this repo's `findmy/keys/` (gitignored — key
material never gets committed). **Back it up somewhere private**; without
it you can't reflash the tag or ever use the Apple Find My backend for it.

## 2. Build the firmware (with battery reporting)

Our firmware in [firmware-tag/](../firmware-tag/) is go-haystack's beacon
plus real battery telemetry (level + precise %). Overlay it and build with
the tag's **Advertisement key** (the base64 line in the `.keys` file):

```bash
cp <this-repo>/firmware-tag/*.go go-haystack/firmware/
cd go-haystack/firmware
tinygo build -target=xiao-ble -o tag-04.uf2 \
  -ldflags "-X main.AdvertisingKey=<ADV_KEY_BASE64>" .
```

(Skipping the `cp` gives you stock go-haystack firmware: works fine, but
battery always reads "full" — the dashboard shows no real level or %.)

## 3. Flash

1. Plug the XIAO in over USB-C.
2. Double-tap the tiny reset button — a UF2 bootloader drive appears
   (`XIAO-SENSE` or similar).
3. Copy `tag-04.uf2` onto the drive. It reboots and starts advertising
   immediately.

## 4. Register the tag on the server

The tag's BLE MAC is derived from its advertisement key (first 6 bytes,
top two bits set). Compute it:

```bash
python tools/mac_from_key.py findmy/keys/tag-04.keys
# -> e.g. C7:11:22:33:44:55
```

Add it to [server/tags.json](../server/tags.json):

```json
{
  "C6:8C:B5:57:0E:16": "keyring",
  "C7:11:22:33:44:55": "tag-04"
}
```

Restart the server (`server/start-server.bat`) — tags.json is read at startup.

## 5. Verify before soldering

With the board still on USB power:

```bash
python tools/scan_tags.py
```

Expect a line like:

```
C7:11:22:33:44:55  rssi  -60  adverts   3  batt full / 100%  -> REGISTERED as 'tag-04'
```

- Requires the PC's Bluetooth ON — `tools/enable-bluetooth.ps1` does it
  from a shell.
- Windows batches duplicate adverts, so a handful of reports per 30 s
  scan is normal even though the tag transmits every 1.3 s.
- `batt ... / n/a (stock/old fw)` means the tag runs stock go-haystack or
  a pre-battery build of our firmware — reflash with step 2 if you want
  real battery readings.

If the listener + server are already running, the tag also appears on the
dashboard (`http://localhost:8000`) within one listener cycle.

## 6. Battery

Solder the LiPo to the **BAT +/−** pads on the XIAO's underside. The board
has an onboard charger: plugging USB-C in charges the cell (~50 mA default).

Battery telemetry comes from the onboard divider (P0.14 enable, P0.31 ADC);
the firmware prints `batt mv <mV> pct <p>` on USB serial for the first ~16 s
after boot. If a board's reading is off against a multimeter, adjust the
constants in [firmware-tag/mcu.go](../firmware-tag/mcu.go) (see
[firmware-tag/README.md](../firmware-tag/README.md)). Expect months per
charge — the beacon duty cycle is AirTag-class.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `scan_tags.py` hears nothing at all | Bluetooth off (`tools/enable-bluetooth.ps1`), or tag unpowered |
| Beacon heard but `not in tags.json` | MAC mismatch — re-derive with `mac_from_key.py`, check you used the *advertisement* key; server restart needed after editing tags.json |
| `batt n/a` on our firmware | Board flashed with stock/pre-battery firmware — rebuild with the `cp firmware-tag/*.go` overlay |
| No UF2 drive on double-tap | Try double-tapping faster; or plug in while holding reset |
| `public key must be 28 bytes long` on serial | Wrong or truncated `-X main.AdvertisingKey` value — pass the base64 advertisement key exactly |
| Tag on dashboard but no map pin | Listener has no coordinates: add the zone to `server/landmarks.json` (copy from `landmarks.example.json`) or pass `--lat/--lon` to listener.py |

## Other tag hardware

Classic ESP32 boards and $3 ST17H66 iTag clones also work (stock
Macless-Haystack firmware, no battery telemetry) — see
[findmy/README.md](../findmy/README.md). They use the same key scheme, so
registration is identical: `mac_from_key.py` + tags.json.
