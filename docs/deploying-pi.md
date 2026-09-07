# Deploying to a Raspberry Pi

The Pi is the best host for this project because it does **both jobs**: it
serves the dashboard *and*, using its own Bluetooth radio, listens for your
tags around the clock. That second part is what a cloud VM can't do — see
[deploying.md](deploying.md) if you'd rather host in the cloud.

```
tags --BLE--> Pi (listener + server + SQLite) --Tailscale--> your phone
```

**Time:** about an hour, most of it waiting on downloads.

## 1. Flash the card — this is where the settings live

Nearly every "I can't find my Pi" problem starts here. Raspberry Pi OS
ships with WiFi unconfigured and SSH **disabled**, so a card flashed
without settings produces a Pi that boots perfectly and stays invisible.

1. Install [Raspberry Pi Imager](https://www.raspberrypi.com/software/).
2. **Device:** your Pi model. **OS:** *Raspberry Pi OS (other)* →
   **Raspberry Pi OS Lite (64-bit)**. Lite has no desktop — right for a
   headless box, and ~2.5 GB instead of ~11 GB.
3. **Storage:** your microSD.
4. Click **Next**, then — the critical step — **Edit Settings**:
   - **Hostname:** `tracker` (it becomes `tracker.local`)
   - **Username and password:** set both; note them down
   - **Configure wireless LAN:** SSID and password, exactly as typed.
     Use a network the Pi can actually see; if your router splits 2.4 GHz
     and 5 GHz into separate names, either works on a Pi 4/5.
   - **Wireless LAN country:** required, or WiFi stays off
   - **Services tab → Enable SSH** → *Use password authentication*
5. Save, write, wait for verification.

If you skip step 4, re-flash. There's no way to fix it from the running Pi
without a monitor and keyboard.

## 2. First boot

Insert the card, power up, and give it **2–3 minutes** — the first boot
resizes the filesystem and reboots once.

Then, from your PC:

```bash
ping tracker.local
ssh <your-username>@tracker.local
```

If the name doesn't resolve, find it by IP instead:

```bash
# Windows: sweep the LAN, then look for a Raspberry Pi MAC prefix
for /L %i in (1,1,254) do @ping -n 1 -w 200 192.168.1.%i >nul
arp -a | findstr /i "2c-cf-67 d8-3a-dd dc-a6-32 e4-5f-01 b8-27-eb"
```

Those prefixes are Raspberry Pi's; `2c-cf-67` and `d8-3a-dd` are the Pi 5.
Nothing at all usually means the WiFi credentials didn't take — re-flash
with step 4 done, or plug in ethernet, which needs no configuration.

## 3. Install

```bash
sudo apt update && sudo apt install -y python3-venv git
sudo useradd -r -m -d /var/lib/tracker tracker
# Bluetooth scanning goes through BlueZ over D-Bus, which requires
# membership of the bluetooth group.
sudo usermod -aG bluetooth tracker

sudo git clone https://github.com/yashpatel1314/custom_airtag /opt/custom_airtag
sudo python3 -m venv /opt/custom_airtag/.venv
sudo /opt/custom_airtag/.venv/bin/pip install \
  -r /opt/custom_airtag/server/requirements.txt bleak
sudo mkdir -p /var/lib/tracker && sudo chown tracker:tracker /var/lib/tracker
```

`bleak` is installed alongside the server requirements because the Pi runs
the listener too.

## 4. Configure

```bash
sudo cp /opt/custom_airtag/deploy/tracker.env.example /etc/tracker.env
sudo nano /etc/tracker.env
sudo chmod 600 /etc/tracker.env && sudo chown tracker:tracker /etc/tracker.env
```

- `API_TOKEN` — generate one:
  `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`
- `DASH_PASSWORD` — **required.** The server refuses to start without it,
  because a blank value would serve your location history to anyone who
  reaches the Pi.
- `SESSION_SECRET` — leave blank; one is generated and persisted.
- `RETENTION_DAYS` — 90 by default. Sightings are ~0.5 GB/year for three
  tags, so this bounds SD card growth.

## 5. Run both services

```bash
sudo cp /opt/custom_airtag/deploy/tracker.service /etc/systemd/system/
sudo cp /opt/custom_airtag/deploy/tracker-listener.service /etc/systemd/system/
sudo systemctl enable --now tracker tracker-listener
sudo systemctl status tracker tracker-listener      # both: active (running)
```

Check the listener is hearing things:

```bash
sudo journalctl -u tracker-listener -f
# expect lines like: 14:22:31 heard 2, ours: ['keyring']
```

`no beacons` means it's scanning but nothing is in range — confirm a tag is
actually alive (`python3 /opt/custom_airtag/tools/scan_tags.py`).

Local check: `curl -s localhost:8000/healthz` → `{"ok":true}`

## 6. Reach it from your phone

**Tailscale** is the simplest option — no ports opened, no certificates, no
dynamic DNS:

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

Follow the printed URL to authorise. Install the Tailscale app on your
iPhone, sign in to the same account, and the Pi is reachable at the name
Tailscale assigns (`http://tracker`, or its `100.x.y.z` address) from
anywhere, including cellular.

To install the dashboard as an app, open that address **in Safari** →
Share → **Add to Home Screen**.

> Tailscale serves plain http, on which browsers refuse `Secure` cookies.
> Either add `COOKIE_SECURE=0` to `/etc/tracker.env` (safe here — the
> Tailscale network is already private and encrypted), or use
> `sudo tailscale serve --bg 8000` to get a real HTTPS `*.ts.net` name and
> leave cookies secure. The second is preferable.

For a **public** HTTPS URL instead, follow steps 2–3 and 6–7 of
[deploying.md](deploying.md) — port forwarding, DuckDNS, and Caddy work the
same on a Pi, at the cost of exposing a login page to the internet.

## 7. Point your tags' zone name

The Pi's listener reports zone `home` by default. To place a map pin
rather than showing zone-only presence, create
`/opt/custom_airtag/server/landmarks.json`:

```json
{"home": {"lat": 43.6532, "lon": -79.3832, "label": "Home"}}
```

Then `sudo systemctl restart tracker`. Coordinates come from right-clicking
your address in Google Maps.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Can't find the Pi at all | WiFi/SSH not set in Imager (step 1.4). Re-flash, or use ethernet. |
| `tracker.service` won't start | `journalctl -u tracker -n 30`. A `DASH_PASSWORD is not set` error means `/etc/tracker.env` is incomplete. |
| Listener logs `post failed: HTTP Error 401` | `API_TOKEN` mismatch, or the unit isn't reading `/etc/tracker.env`. |
| Listener sees nothing, ever | `hciconfig` should list `hci0` as `UP RUNNING`. If the tracker user was just added to `bluetooth`, restart the service. |
| Login succeeds then bounces back | `Secure` cookies over plain http — see the Tailscale note in step 6. |
| Dashboard fine, tags frozen | The listener is down; `systemctl status tracker-listener`. |
