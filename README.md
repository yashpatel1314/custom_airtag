# custom_airtag

DIY trackers with a self-hosted web UI. Two builds, depending on what you
want to spend:

| | **Build C: BLE tags + own receivers** (primary) | **Build A: Find My beacon** ([findmy/](findmy/)) | **Build B: GPS + LTE-M** (below) |
|---|---|---|---|
| Cost per tag | **~$15 fixed** (XIAO nRF52840 + LiPo) | $3–10 fixed | ~$45–60 |
| Recurring cost | **$0** | $0 | ~$1–2/mo (SIM data) |
| Battery | months per charge | coin cell, weeks–months | 18650, 1–2 weeks |
| Coverage | wherever you place ESP32 listener nodes | anywhere iPhones pass (needs an Apple ID for the backend) | anywhere with cellular |
| Update rate | **seconds** (in coverage) | passive — minutes to hours | your chosen interval |
| Apple involvement | **none** | rides Apple's network, E2E-encrypted | none |

**Build C is the primary build**: same tags as Build A (they broadcast the
same beacon format), heard by your own ESP32 listener nodes
([firmware-listener/](firmware-listener/)) instead of strangers' iPhones.
Within your coverage it beats an AirTag outright — second-level updates,
full history/trails, unlimited tags, open API, web UI on any device. What it
gives up is global crowd coverage; Build A adds that back anytime by
finishing the Apple ID login in [findmy/](findmy/) — the tags need no
change. Build B is the "track a car across the country" option; a cellular
radio always needs a data plan, so it can't be fixed-price.

## Build C: BLE tags + listener nodes

1. Flash tags (see [findmy/README.md](findmy/README.md) — `haystack keys`
   + `haystack flash`, or build the UF2 with TinyGo directly).
2. Register each tag's MAC in [server/tags.json](server/tags.json) — the MAC
   is derived from the advertisement key (first 6 bytes, top two bits set).
3. For each zone (home, garage, office...): edit
   [firmware-listener/include/config.h](firmware-listener/include/config.h)
   (WiFi, server URL, token, zone name, position) and flash any classic
   ESP32 devkit: `pio run -t upload` in `firmware-listener/`.
4. Run the server (below). Dashboard shows each tag's zone, signal, map pin,
   and trail.

A listener without coordinates (e.g. powered from a car's USB) reports
zone-only presence: "tag-03 · at car".

---

## Build B: self-hosted GPS tracker

Works anywhere with cellular coverage, reports to **your own** web dashboard,
zero dependence on Apple/Google. One board, one Python server, one SIM.

```
┌─────────────────────┐   LTE-M (Hologram SIM)   ┌──────────────────────┐
│ LILYGO T-SIM7000G   │ ───── HTTP POST ───────► │ server/app.py        │
│ ESP32 + GPS + LTE-M │      /api/ping           │ FastAPI + SQLite     │
│ wakes every N min,  │                          │ + Leaflet dashboard  │
│ deep-sleeps between │                          │ (any old PC / free   │
└─────────────────────┘                          │  cloud VM / Pi)      │
                                                 └──────────────────────┘
```

## Bill of materials

| Item | What / where | Cost |
|---|---|---|
| **LILYGO T-SIM7000G** | ESP32 + SIM7000G (LTE CAT-M/NB-IoT/2G + GPS), 18650 holder, solar charge input, GPS + LTE antennas included. Amazon ≈ $43–51, AliExpress ≈ $32–38 | ~$35–50 |
| **18650 Li-ion cell** | 3000–3500 mAh (Samsung 35E, LG MJ1, etc.). Snaps into the holder on the back of the board | ~$6–8 |
| **Hologram IoT SIM** | Pay-as-you-go: $0.03/MB + ~$1/mo platform fee. This tracker uses ≈1 MB/month at 15-min pings | $3 one-time, ~$1–2/mo |
| *(optional)* 5–6 V solar panel | Wires into the board's solar input (4.4–6 V), makes charging a non-issue outdoors | ~$8 |
| *(optional)* enclosure | 3D-printed box; keep the GPS antenna face-up with sky view | filament |

**Total: ~$45–60 up front, ~$1–2/month.** No other hardware — the board has
everything integrated, there is **no wiring**: insert SIM, clip in the battery,
plug in the two antennas (u.FL connectors, labeled GPS and MAIN/LTE).

Server hosting is $0: any always-on machine at home (port-forward one port),
or an always-free cloud VM (e.g. Oracle Cloud free tier).

## 1. Server setup

```bash
cd server
pip install -r requirements.txt
API_TOKEN="some-long-random-secret" uvicorn app:app --host 0.0.0.0 --port 8000
```

or Docker: `docker build -t tracker . && docker run -p 8000:8000 -e API_TOKEN=... -v tracker-data:/data tracker`

Open `http://<host>:8000` — that's the dashboard. The tag needs to reach this
host from the internet, so either run it on a cloud VM or port-forward 8000 on
your router to the machine running it.

### Test it before the hardware arrives

```bash
python tools/simulate_tracker.py http://127.0.0.1:8000 tag-01
```

posts fake pings in the exact format the firmware sends; the dashboard should
show a pin moving in a loop with battery/signal tiles updating.

## 2. SIM setup

1. Order a [Hologram](https://www.hologram.io/) SIM, activate it in their
   dashboard on the pay-as-you-go plan.
2. Punch the card out to **nano** size — that's what the board's slot takes.
3. Check [LTE CAT-M coverage](https://www.hologram.io/coverage/) for your
   carrier region — in the US all three major carriers run CAT-M.

## 3. Firmware setup

1. Edit [firmware/include/config.h](firmware/include/config.h):
   `SERVER_HOST`, `SERVER_PORT`, `API_TOKEN` (must match the server),
   `SLEEP_MINUTES` (battery life scales with it).
2. Flash (install [PlatformIO](https://platformio.org/), then):

```bash
cd firmware
pio run -t upload && pio device monitor
```

3. First boot outdoors: GPS cold start takes 30–60 s with sky view. The LED
   blinks while searching, then you'll see `Fix: <lat>,<lon>` and `HTTP 200`
   in the monitor, and the tag appears on the dashboard.

## Battery expectations (honest numbers)

Deep-sleep draw on this board is ~1–2 mA; each wake cycle (GPS fix + LTE
attach + POST) averages ~100–150 mA for 1–3 minutes. On a 3000 mAh 18650:

| Report interval | Approx. runtime |
|---|---|
| 15 min | 1–2 weeks |
| 60 min | 4–6 weeks |
| 6 h | months |
| any + small solar panel | indefinite |

This is the physics of GPS+cellular — no coin-cell-for-a-year like a real
AirTag, because an AirTag never runs a GPS receiver or a cellular radio; it
borrows iPhones for both.

## Security notes

- Transport is plain HTTP (the SIM7000's TLS stack is slow/flaky); the
  `X-Token` header gates writes, and reads are open by default. If the
  dashboard should be private, put the server behind a reverse proxy with
  auth for GET routes, and keep `/api/ping` reachable for the tag.
- Use a long random `API_TOKEN`; the default in the repo is a placeholder.

## Troubleshooting

- **No network**: check APN (`hologram`), and that your area has CAT-M
  coverage. Try `modem.setNetworkMode(13)` (2G) as a fallback where CAT-M is
  absent (SIM7000G supports it; higher power draw).
- **No GPS fix indoors**: normal. The firmware reports `fix: false` pings so
  you still see battery/signal, and the dashboard shows the last known
  position, greyed with its age.
- **Modem never answers AT**: battery must be inserted — USB power alone
  can't supply LTE transmit peaks.

## Transferring to another machine

Everything is in git EXCEPT secrets. After cloning, carry these over
manually (USB stick / anything private — never commit them):

- `findmy/keys/` — your tags' private keys. Without these you cannot
  reflash tags or (later) decrypt Find My reports. Back them up!
- `firmware-listener/include/config.h` — copy from `config.h.example`,
  fill in WiFi + token (or bring your existing one).
- `server/start-server.bat` / `start-listener.bat` — copy from the
  `.example` versions and insert your token.
- `server/tracker.db` — only if you want to keep location history.

Server setup on the new machine: `pip install fastapi uvicorn bleak`,
then run the server and (if it has Bluetooth) `python listener.py`.
