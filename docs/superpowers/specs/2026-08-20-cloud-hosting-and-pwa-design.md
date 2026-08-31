# Cloud hosting + phone app — design

**Status:** approved 2026-08-20, pending implementation plan
**Goal:** reach the tracker dashboard privately from an iPhone anywhere,
installed like an app, at $0/month.

## Problem

Today the server runs on a Windows PC and is reachable only at
`http://localhost:8000`. The PC is not on 24/7 and there is no
authentication, so the dashboard cannot simply be exposed to the internet:
it shows live locations of the owner's belongings.

## Goals / non-goals

**Goals**

- Dashboard reachable over HTTPS from anywhere, private to the owner.
- Installs on iPhone as a full-screen app with its own icon.
- $0/month recurring.
- Existing BLE listeners keep working with minimal change.
- Local development is unchanged (no auth needed on localhost).

**Non-goals**

- Native iOS app (App Store, push notifications). A PWA is the right size.
- Multi-user accounts or per-tag sharing. Single owner only.
- Moving BLE reception to the cloud — radios stay at home by definition.

## Architecture

```
XIAO tags --BLE--> PC listener (home)  -+
                   future ESP32 nodes  -+ HTTPS POST /api/sighting (X-Token)
                                        v
                            Oracle always-free VM (Ubuntu)
                            Caddy :443  --reverse_proxy-->  uvicorn :8000
                            (Let's Encrypt, auto-renew)     FastAPI + SQLite
                                        ^
                                        | HTTPS + session cookie
                              iPhone PWA / any browser
```

Hostname: free `*.duckdns.org` subdomain pointed at the VM's reserved
public IP. Caddy obtains and renews certificates automatically.

**Known limitation (accepted):** the *dashboard* is always up, but new
*sightings* only arrive while a listener at home is running. With only the
PC listener, sightings pause when the PC sleeps; the dashboard then shows
the last known position with its age, which it already does today. A ~$5
always-on ESP32 node removes this gap later — the design keeps that path
open, which is why the token-based write API is retained.

## Components

### 1. Authentication (`server/auth.py`, new)

Read routes gain a session gate; write routes keep the existing token.

| Route | Protection |
|---|---|
| `/`, `/api/devices`, `/api/devices/{d}/history` | session cookie |
| `/api/sighting`, `/api/ping` | `X-Token` header (unchanged) |
| `/login`, `/logout`, `/healthz`, `/static/*` | public |

- **Password:** `DASH_PASSWORD` env var, compared with
  `hmac.compare_digest`.
- **Session cookie:** `tracker_session` = `<expiry>.<hmac_sha256(expiry,
  secret)>`; `HttpOnly`, `Secure`, `SameSite=Lax`, 180-day lifetime so the
  phone logs in once. `/logout` clears it.
- **Secret:** `SESSION_SECRET` env var; if unset, generated once and
  persisted next to the DB so restarts do not log the phone out.
- **Rate limit:** in-memory, 10 failed attempts per IP per 15 min, then
  429. Sufficient for a single-user deployment.
- **Backward compatibility:** when `DASH_PASSWORD` is unset, every route
  behaves exactly as today. Local development and the existing
  `start-server.bat` are unaffected.

`/static/*` stays public deliberately: it holds only CSS/JS/icons, no
location data, and keeping it open avoids breaking the PWA manifest and
service-worker fetches at the login screen.

### 2. PWA (`server/static/`)

- `manifest.webmanifest` — name, `display: standalone`, theme colors,
  192/512 icons (regular + maskable).
- iOS meta tags in `index.html`: `apple-mobile-web-app-capable`,
  status-bar style, title, and a 180px `apple-touch-icon`.
- `sw.js` — cache-first for the app shell so it opens instantly offline;
  **network-only for `/api/*`**, since a cached location is a misleading
  location.
- Icons generated during implementation (simple tag/pin mark).

Install flow on iPhone: Safari, Share, **Add to Home Screen**. The
Android/Chrome flow is documented alongside it for completeness.

### 3. Deployment kit (`deploy/`, new)

- `Caddyfile` — hostname plus `reverse_proxy 127.0.0.1:8000`.
- `tracker.service` — systemd unit running uvicorn as a non-root user,
  `EnvironmentFile=/etc/tracker.env`, `Restart=always`.
- `tracker.env.example` — `API_TOKEN`, `DASH_PASSWORD`, `SESSION_SECRET`,
  `DB_PATH=/var/lib/tracker/tracker.db`.

### 4. Documentation (`docs/deploying.md`, new)

Oracle account, always-free VM (Ampere A1; x86 micro as fallback),
reserved public IP, **both** firewall layers, DuckDNS, clone and install,
systemd and Caddy, first login, iPhone install, and pointing the home
listener at the cloud URL.

The two-firewall step is called out explicitly: Oracle requires opening
ports in the VCN security list *and* in the instance's own iptables rules,
which Ubuntu images ship locked down. Missing the second is the most
common failure, and it looks exactly like a broken Caddy certificate.

### 5. Firmware touch-up (`firmware-listener/`) — deferred

Accept `https://` in `SERVER_URL`, bundling the Let's Encrypt ISRG Root X1
certificate via `WiFiClientSecure::setCACert`, with `setInsecure()`
documented as the fallback if that root ever rotates.

**Deferred to Phase 3.** No ESP32 node is deployed yet, and the PC listener
already speaks HTTPS, so nothing in Phase 1 or 2 depends on this. Building
it now would be speculative work against hardware that does not exist.

## Data and secrets

- Start with a **fresh** database on the VM. The local `tracker.db` holds
  a day of test data and is not worth migrating.
- Generate a **new** `API_TOKEN` for the cloud: the current one was only
  ever used on the LAN, and it will now travel the internet.
- `deploy/tracker.env` is gitignored; only `.example` is committed,
  matching how the repo already handles `config.h` and the `.bat` files.

## Error handling

- Wrong password: login page re-renders with an error, leaking no detail.
- Expired or invalid cookie: redirect to `/login`.
- Listener cannot reach the cloud: it already logs `post failed:` and
  retries next cycle; no data loss beyond that window.
- Server down: Caddy returns 502; systemd restarts uvicorn.
- `/healthz` returns 200 for uptime checks.

## Verification

Locally, before touching the VM:

- anonymous `GET /api/devices` returns 401; after login, 200
- wrong password rejected; 11th attempt returns 429
- `POST /api/sighting` with `X-Token` still works with no session
- with `DASH_PASSWORD` unset, every route behaves as today
- manifest, icons, and service worker are served

On the VM:

- HTTPS smoke test with a valid certificate
- the PC listener posts real sightings to the cloud
- the `keyring` tag appears on the iPhone **over cellular**, not just WiFi
- the app installs to the home screen and opens standalone

Tests use FastAPI's `TestClient`, adding `pytest` and `httpx` as dev
dependencies, since the repo currently has no test suite.

## Rollout

1. **Phase 1 — auth + PWA**, verified locally.
2. **Phase 2 — cloud deploy**, verified from the phone over cellular.
3. **Phase 3 — the other two tags** (`tag-02`, `tag-03`): power them,
   confirm with `tools/scan_tags.py`, then confirm they reach the cloud
   dashboard. Their MACs are already registered in `server/tags.json`, so
   tracking needs no reflash.
   **Blocker to resolve first:** `findmy/keys/` is empty on this PC, so
   neither tag can be reflashed. That matters only for the precise
   battery-percentage firmware — plain tracking works without the keys.
   The `keyring` tag is in the same position (pre-percentage firmware).
   Phase 3 also picks up the deferred ESP32 HTTPS work if an always-on
   listener node is added to close the coverage gap.

## Risks

| Risk | Mitigation |
|---|---|
| Oracle reclaims idle always-free VMs | Accepted; the deploy kit makes rebuilding short. A paid ~$5 VPS is a drop-in fallback. |
| Public login page attracts bots | Rate limiting, long random password, no user enumeration. |
| Phone logged out unexpectedly | Persisted `SESSION_SECRET` survives restarts and redeploys. |
| Home listener offline | Known limitation above; an ESP32 node is the fix. |
