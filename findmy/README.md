# The under-$10 tag — Find My beacon (fixed price, no subscription)

This build beats an AirTag on price by using the same trick an AirTag uses:
it doesn't locate itself. The tag is a dumb BLE beacon; every iPhone that
walks past it anonymously uploads its position to Apple's Find My network,
end-to-end encrypted with **your** key — Apple never sees the location, and
neither can anyone without your private key. The self-hosted backend here
([Macless-Haystack](https://github.com/dchristl/macless-haystack)) pulls
those encrypted reports and shows them in a web UI. No Apple hardware —
just a free Apple ID.

**Cost per tag: $3–10. Recurring cost: $0.** No SIM, no plan, no server fees
(the two Docker containers run on your PC).

## Tag hardware — pick one

| Option | Parts | Cost/tag | Battery life | Effort |
|---|---|---|---|---|
| **Seeed XIAO nRF52840** (recommended) | board ~$10 (3-pack ~$28 Amazon) + 500 mAh LiPo ~$5 (solders to BAT pads, onboard charger) | ~$14 | **months per charge** — AirTag-class chip | flash over USB with [go-haystack](https://github.com/hybridgroup/go-haystack): `haystack flash` |
| **Classic ESP32 (WROOM/WROVER devkit)** — free if you own some | board ~$5–6 + LiPo/USB power | ~$0–10 | days–weeks (ESP32 idle draw is high) | official prebuilt firmware, `esptool write_flash` |
| **iTag clone reflash** (cheapest, comes with case) | $2–4 ST17H66 iTag from AliExpress + one-time USB-UART adapter ~$2 | ~$3–4 | ~2 months per coin cell, case + battery included | solder 4 wires once to flash |

> **ESP32-C3 boards (XIAO ESP32C3, C3 Supermini) are NOT supported** by the
> prebuilt Macless-Haystack firmware — it targets classic ESP32 only (the C3
> is a different RISC-V core), and no maintained C3 port exists as of
> mid-2026. Don't buy C3 boards for this build.

The ESP32 and ST17H66 options use precompiled firmware from the
[Macless-Haystack releases](https://github.com/dchristl/macless-haystack/releases);
the XIAO nRF52840 uses [go-haystack](https://github.com/hybridgroup/go-haystack),
whose output plugs into the same Macless-Haystack backend and web UI.

## Setup

### 1. Generate your keypair

```bash
pip install cryptography
# download generate_keys.py from the releases page, then:
python generate_keys.py
```

Produces a `.keys` file (private key stays with you) and the key material to
bake into the firmware.

### 2. Flash the tag

Download the prebuilt firmware for your board from the releases page, insert
your advertisement key per its instructions, flash (ESP32: `esptool`/USB;
nRF: ST-Link; ST17H66: USB-UART). The tag starts advertising immediately and
nearby iPhones begin relaying it within minutes.

### 3. Start the backend (this folder)

```bash
docker compose run --rm -it endpoint   # first run: logs into your Apple ID
docker compose up -d                   # afterwards: run detached
```

Requirements: an Apple ID with **SMS-based** two-factor auth (that's the only
2FA method the login flow supports). Use a throwaway/dedicated Apple ID if
you prefer — it needs no purchases and no devices.

### 4. View your tags

Open the web frontend at <https://dchristl.github.io/macless-haystack/> and
point it at your endpoint (`http://localhost:6176`), or use their Android
app. Location data flows only between your endpoint and Apple; the hosted
frontend is just static JS talking to your local server.

## Expectations

- **Update latency**: minutes in cities (lots of passing iPhones), hours in
  the middle of nowhere. An AirTag has the same property — this network *is*
  passing iPhones.
- **No anti-stalking protections**: unlike a retail AirTag, this won't
  trigger "unknown tracker" alerts on someone's phone. Only put it on your
  own stuff.
- **Longevity risk**: this rides a reverse-engineered Apple protocol. It has
  survived years of Apple updates, but Apple could break it someday. Worst
  case, your $3 tags still work as plain BLE beacons for the GPS build in
  the repo root.
