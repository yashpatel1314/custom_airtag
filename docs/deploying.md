# Deploying to the internet (free VM + HTTPS + phone app)

Puts the dashboard on a public HTTPS address, private behind a password,
installable on an iPhone as a full-screen app. Recurring cost: $0.

**What this changes and what it does not.** The *dashboard* becomes
reachable from anywhere. *Sightings* still only arrive while a listener at
home is running — your PC listener, or an ESP32 node. When nothing at home
is listening, the dashboard shows the last known position with its age.

```
tags --BLE--> listener at home --HTTPS /api/sighting--> VM --HTTPS--> your phone
```

## 1. Create the VM

[Oracle Cloud](https://cloud.oracle.com) always-free tier (signup needs a
card; it is not charged on always-free shapes).

1. **Compute → Instances → Create instance.**
2. Shape: **VM.Standard.A1.Flex** (Ampere, 4 OCPU / 24 GB free). If capacity
   is unavailable in your region, **VM.Standard.E2.1.Micro** works fine —
   this app is tiny.
3. Image: **Ubuntu 24.04**.
4. Save the SSH private key it offers. You cannot re-download it.
5. After creation: **Reserve** the public IP (Instance → Attached VNICs →
   IP addresses → edit the public IP → Reserved). An ephemeral IP changes
   on stop/start and breaks your DNS.

SSH in: `ssh -i <key> ubuntu@<public-ip>`

## 2. Open the firewall — both layers

This is the step that wastes people's afternoons. Oracle has **two**
independent firewalls and you must open both.

**Layer 1 — VCN security list** (in the web console): Networking → your VCN
→ Security Lists → default → Add Ingress Rules. Source `0.0.0.0/0`, TCP,
destination ports **80** and **443**.

**Layer 2 — the instance's own iptables**, on the VM:

```bash
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
sudo netfilter-persistent save
```

> Ubuntu images on Oracle ship with everything but SSH blocked locally.
> If you skip this, Caddy cannot complete the ACME challenge and reports a
> certificate failure — which sends you debugging TLS when the real problem
> is a closed port.

## 3. Point a hostname at it

Free: [DuckDNS](https://www.duckdns.org) — sign in, pick a subdomain, set
its IP to your reserved public IP. Wait for
`nslookup <you>.duckdns.org` to answer before continuing; Caddy needs
working DNS to get a certificate.

## 4. Install the app

```bash
sudo apt update && sudo apt install -y python3-venv git
sudo useradd -r -m -d /var/lib/tracker tracker
sudo git clone https://github.com/yashpatel1314/custom_airtag /opt/custom_airtag
sudo python3 -m venv /opt/custom_airtag/.venv
sudo /opt/custom_airtag/.venv/bin/pip install -r /opt/custom_airtag/server/requirements.txt
sudo mkdir -p /var/lib/tracker && sudo chown tracker:tracker /var/lib/tracker
```

## 5. Configure secrets

```bash
sudo cp /opt/custom_airtag/deploy/tracker.env.example /etc/tracker.env
sudo nano /etc/tracker.env
sudo chmod 600 /etc/tracker.env && sudo chown tracker:tracker /etc/tracker.env
```

Fill in:

- `API_TOKEN` — generate a **new** one; the LAN token was never meant to
  cross the internet:
  `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`
- `DASH_PASSWORD` — the dashboard password. Long and random; you type it
  once per device, so length costs you nothing.
- `SESSION_SECRET` — leave blank. One is generated and persisted beside the
  database, so restarts do not log your phone out.

## 6. Start the services

```bash
sudo cp /opt/custom_airtag/deploy/tracker.service /etc/systemd/system/
sudo systemctl enable --now tracker
sudo systemctl status tracker          # expect: active (running)
```

Caddy (install per [caddyserver.com/docs/install](https://caddyserver.com/docs/install)):

```bash
sudo cp /opt/custom_airtag/deploy/Caddyfile /etc/caddy/Caddyfile
sudo sed -i "s/YOUR-HOST/<you>.duckdns.org/" /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

Caddy fetches the certificate on first request — allow a few seconds.

## 7. Verify

```bash
curl https://<you>.duckdns.org/healthz     # {"ok":true}
```

Open `https://<you>.duckdns.org` in a browser: you should get the login
page, and your password should take you to the dashboard.

## 8. Point the home listener at the cloud

Edit `server/start-listener.bat` on your PC — replace the server URL with
`https://<you>.duckdns.org` and the token with the cloud `API_TOKEN`:

```bat
python listener.py --server https://<you>.duckdns.org --token <cloud-API_TOKEN> --listener home
```

Run it and confirm the tag appears on the cloud dashboard. Any ESP32
listener nodes need the same two values in
`firmware-listener/include/config.h`.

## 9. Install on your iPhone

1. Open `https://<you>.duckdns.org` **in Safari** (Chrome on iOS cannot
   install web apps).
2. Sign in — the session lasts 180 days, so this is a one-time step.
3. Share button → **Add to Home Screen** → Add.

It now launches full-screen with its own icon, no browser chrome.

*Android, for reference:* Chrome shows an **Install app** prompt, or use
menu → Add to Home screen.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Caddy cannot get a certificate | Almost always the instance iptables (step 2, layer 2). Verify with `curl http://<ip>` from elsewhere; a hang means the port is closed. |
| 502 from Caddy | The app is down: `sudo systemctl status tracker`, `sudo journalctl -u tracker -n 50`. |
| Login form accepts the password but loops back | Cookies are marked `Secure`, so they are dropped over plain http. Browse via `https://`, or set `COOKIE_SECURE=0` for local http testing only. |
| Listener logs `post failed: HTTP Error 401` | `API_TOKEN` mismatch between `/etc/tracker.env` and the listener. |
| "Too many attempts" | Ten failed logins from one IP; wait 15 minutes or restart the service. |
| Dashboard loads but tags look frozen | Nothing at home is listening. Expected when the PC sleeps — see the note at the top. |
| Tag missing entirely | Check it is still broadcasting: `python tools/scan_tags.py` on the PC. |

## Local development is unchanged

With no `DASH_PASSWORD` set, the server behaves exactly as it always has —
no login, open on localhost. `server/start-server.bat` needs no edits.
