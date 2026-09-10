# Deploying to a Raspberry Pi

The Pi is the best host for this project because it does **both jobs**: it
serves the dashboard *and*, using its own Bluetooth radio, listens for your
tags around the clock. That second part is what a cloud VM can't do — see
[deploying.md](deploying.md) if you'd rather host in the cloud.

```
tags --BLE--> Pi (listener + server-in-a-container) --Tailscale--> your phone
```

The server runs in a **Podman** container (rootless, no root daemon); the
BLE listener runs as a plain native process. Containerizing the listener too
would need `--privileged` or host networking for BlueZ/D-Bus access, which
trades away most of the isolation benefit for the one piece where
reliability matters more than sandboxing — so it stays native.

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
   - **Username and password:** set both; note them down. Pick a password
     with **only letters and numbers** — no `@` or other punctuation. If
     the keyboard layout ever ends up wrong (see troubleshooting), typing
     a symbol-free password sidesteps the entire problem.
   - **Configure wireless LAN:** SSID and password, exactly as typed.
     Use a network the Pi can actually see; if your router splits 2.4 GHz
     and 5 GHz into separate names, either works on a Pi 4/5.
   - **Wireless LAN country:** required, or WiFi stays off
   - **Services tab → Enable SSH** → **"Use password authentication."**
     Not "Allow public-key authentication only" — that leaves you with no
     way in at all unless you also paste a public key in the same step
     (worth doing anyway: paste your own `~/.ssh/id_ed25519.pub` here if
     you have one, so you never need the password over the network again).
   - **General tab → Locale → Keyboard layout:** set this explicitly to
     match your physical keyboard (e.g. US). Leaving it on Imager's
     default has caused real, hours-long trouble in practice — a
     mismatched layout silently changes which key produces `@`, `/`, and
     other punctuation, which is exactly the character set your password
     and most Linux commands use.
5. Save, write, wait for verification.

If you skip step 4, re-flash. There's no reliable way to fix WiFi, SSH, or
keyboard settings from the running Pi without a monitor and keyboard, and
if the keyboard layout is *also* wrong, you may not even be able to type a
fix.

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

**If `ssh` refuses with `Permission denied (publickey)`**, the "public-key
only" SSH option got selected instead of password auth. Fastest fix without
re-flashing: on the Pi's own console (monitor + keyboard), add a key by
hand — see the "locked out" entry in Troubleshooting below.

## 3. Install Podman and clone the repo

```bash
sudo apt update && sudo apt install -y podman git
git clone https://github.com/yashpatel1314/custom_airtag ~/custom_airtag
```

No separate `python3-venv` package or `bluetooth` group membership is
needed — recent Raspberry Pi OS ships `venv` support built into `python3`,
and BLE scanning over BlueZ's D-Bus API already works for a normal logged-in
user without extra group grants. Confirm both if you want to be sure before
moving on:

```bash
python3 -m venv /tmp/t && rm -rf /tmp/t   # should print nothing, exit 0
bluetoothctl list                          # should print your controller
```

Set up the listener's own environment (it runs natively, outside the
container):

```bash
python3 -m venv ~/custom_airtag/.venv
~/custom_airtag/.venv/bin/pip install -r ~/custom_airtag/server/requirements.txt bleak
```

## 4. Configure secrets

```bash
cp ~/custom_airtag/deploy/tracker.env.example ~/tracker.env
nano ~/tracker.env
chmod 600 ~/tracker.env
```

Fill in:

- `API_TOKEN` — generate one:
  `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`
- `DASH_PASSWORD` — **required.** The server refuses to start without it,
  because a blank value would serve your location history to anyone who
  reaches the Pi.
- `SESSION_SECRET` — leave blank; one is generated and persisted
  automatically next to the database.
- `DB_PATH` — set to `/home/<you>/custom_airtag/server/tracker.db` (the
  listener reads this same file directly; keeping it inside the repo
  checkout avoids needing a separate system directory).
- `RETENTION_DAYS` — 90 by default. Sightings are ~0.5 GB/year for three
  tags, so this bounds SD card growth.

This file lives in your home directory rather than `/etc/` — simpler
permissions, and this whole setup avoids needing root for anything past
the one-time package install above.

## 5. Build and run the containerized server

```bash
podman build -t tracker ~/custom_airtag/server
mkdir -p ~/tracker-data ~/.config/containers/systemd
cp ~/custom_airtag/deploy/tracker.container ~/.config/containers/systemd/
```

That Quadlet unit tells Podman's systemd integration how to run and manage
the container — it sets `DB_PATH=/data/tracker.db` on its own (the path
*inside* the container, pointing at the mounted volume), which is
intentionally different from the `DB_PATH` you set in `tracker.env` for the
listener in the next step, since that one needs the path on the *host*
filesystem instead.

```bash
systemctl --user daemon-reload
systemctl --user start tracker.service
loginctl enable-linger $USER
```

`enable-linger` is the one step that needs `sudo`-equivalent privilege (your
own account can normally run it without a password prompt) — it's what
lets your user-level services keep running, and start again after a
reboot, without you being logged in.

**Quadlet-generated units can't be `systemctl --user enable`d directly** —
that command will fail with "Unit ... is transient or generated," which is
expected. The `[Install]` section in the `.container` file above handles
autostart on its own once `daemon-reload` has run; nothing further is
needed.

Verify it's really the container, not some leftover native process:

```bash
podman ps --format '{{.Names}} {{.Status}} {{.Ports}}'
systemctl --user status tracker.service   # CGroup should show conmon + libpod-payload-...
curl -s localhost:8000/healthz            # {"ok":true}
```

## 6. Run the BLE listener natively

```bash
mkdir -p ~/.config/systemd/user
cp ~/custom_airtag/deploy/tracker-listener.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now tracker-listener.service
```

`PYTHONUNBUFFERED=1` matters here: without it, Python buffers stdout when
it isn't attached to a terminal, so the listener's periodic log lines
(`heard N, ours: [...]`) won't show up in `systemctl status` in real time —
not a functional bug, just an invisible one that makes debugging confusing.

Check it's hearing things:

```bash
systemctl --user status tracker-listener.service --no-pager -l | tail -10
# expect lines like: 14:22:31 heard 2, ours: ['keyring']
```

`ours: []`/`none` means it's scanning but hears no *registered* tag —
confirm one is actually alive and broadcasting:
`python3 ~/custom_airtag/tools/scan_tags.py`.

**If you see `journalctl --user -u tracker-listener` report "No journal
files were found"** — that's a normal Debian quirk where user journals
aren't always separately enabled. Use `systemctl --user status
<name> --no-pager -l` instead, which shows recent log lines directly.

## 7. Reach it from your phone

**Tailscale** is the simplest option — no ports opened, no certificates, no
dynamic DNS, and it works from anywhere your phone has signal, including
cellular:

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale set --operator=$USER   # lets your user run `tailscale` without sudo from now on
tailscale up --ssh
```

Follow the printed URL to authorise. Install the Tailscale app on your
iPhone too, sign in to the same account, and both devices land on the same
private network.

Get a real HTTPS name for the dashboard (required the first time, at your
tailnet's admin console — a link is printed if it isn't on yet):

```bash
tailscale serve --bg 8000
tailscale serve status
```

That prints something like `https://<hostname>.<tailnet>.ts.net` — open
that **in Safari** on your phone, log in, then Share → **Add to Home
Screen** to install it as an app.

> Plain `tailscale up` alone serves over http, which makes browsers refuse
> `Secure` cookies (the login would loop forever). `tailscale serve` is
> what fixes that with a real certificate — don't skip it.

If you ever move networks and lose direct LAN access to the Pi, Tailscale
also solves that: install it on whichever machine you're managing from
(`winget install Tailscale.Tailscale` on Windows), sign in to the same
account, and reach the Pi at its tailnet address
(`tailscale status` on either device prints it) regardless of which local
network either machine is on.

For a **public** HTTPS URL instead (reachable without Tailscale installed
anywhere), follow [deploying.md](deploying.md)'s cloud VM steps — port
forwarding, DuckDNS, and Caddy — adapted to the Pi; that trades away
Tailscale's zero-exposure model for a URL anyone can type.

## 8. Point your tags' zone name

The listener reports zone `home` by default. To place a map pin rather than
showing zone-only presence, create `~/custom_airtag/server/landmarks.json`:

```json
{"home": {"lat": 43.6532, "lon": -79.3832, "label": "Home"}}
```

Then restart the container: `systemctl --user restart tracker.service`.
Coordinates come from right-clicking your address in Google Maps.

## 9. Back up the secrets and data

Everything that matters — your dashboard password, API token, and location
history — lives only on this SD card. Copy it somewhere else periodically:

```bash
scp yashp@<pi-tailscale-ip>:~/tracker.env ./backup/
scp yashp@<pi-tailscale-ip>:~/tracker-data/tracker.db ./backup/
scp yashp@<pi-tailscale-ip>:~/tracker-data/.session_secret ./backup/
```

The `.session_secret` file is worth keeping too — restoring it alongside
the database means an existing browser session doesn't get logged out.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Can't find the Pi at all | WiFi/SSH not set in Imager (step 1.4). Re-flash, or use ethernet. |
| Your PC and the Pi are on different networks now | Install Tailscale on whichever machine you're managing from and reach the Pi at its tailnet address instead of its LAN IP — see step 7. |
| `ssh` says `Permission denied (publickey)` | SSH was set to public-key-only in Imager with no key registered. On the Pi's own console: `mkdir -p ~/.ssh && chmod 700 ~/.ssh && echo '<your-pubkey>' >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys`, then retry from your PC. |
| Typing `@`, `/`, or other symbols produces the wrong character | Keyboard layout mismatch (common if Imager's locale defaulted away from your actual keyboard). Fix: edit `/etc/default/keyboard`, set `XKBLAYOUT="us"` (or your layout), then `sudo setupcon --force`; a reboot afterward confirms it stuck. If you can't type a fix because the very characters you need are the ones affected, look for the `/` on a numeric keypad if you have one — those keys are often exempt from layout remapping. |
| `sudo` keeps asking for a password | Passwordless sudo isn't required by this setup except for the one-time `loginctl enable-linger` in step 5 and the Podman install in step 3 — both are single interactive commands, not something to automate away. |
| `tracker.service` won't start, or runs the wrong thing | Check `systemctl --user status tracker.service` — the `CGroup` line should show `conmon` and `libpod-payload-...` (the container). If it instead shows a path like `.venv/bin/uvicorn`, a stale native unit file with the same name is shadowing the Quadlet; `rm ~/.config/systemd/user/tracker.service` (the static file, not the generated one) and `daemon-reload`. |
| `Failed to enable unit: ... is transient or generated` | Expected for Quadlet units — don't `enable` them; the `.container` file's `[Install]` section handles it after `daemon-reload`. |
| Listener logs `post failed: HTTP Error 401` | `API_TOKEN` mismatch between `tracker.env` and what the listener sent — confirm the same file is referenced by both service units. |
| Listener sees nothing, ever | `bluetoothctl list` should show a controller. If nothing's listed, the radio itself may be off or missing — this isn't a permissions issue on recent Raspberry Pi OS. |
| Login succeeds then bounces back to `/login` | `Secure` cookies over plain http — you skipped `tailscale serve` (step 7) and are hitting the plain `tailscale up` address instead. |
| Dashboard fine, tags frozen | The listener is down; `systemctl --user status tracker-listener.service`. |
| Dashboard reachable but shows old content after a code update | You rebuilt the image but didn't restart the service (`systemctl --user restart tracker.service`), or the browser/PWA is caching a stale page — try a fresh tab with a `?v=2`-style cache-busting query string to rule that out. |
