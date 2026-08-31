# Cloud Hosting + iPhone PWA Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Put the tracker dashboard on the public internet behind HTTPS and a password, installable on an iPhone as a full-screen app, at $0/month.

**Architecture:** A new `server/auth.py` holds all password/session logic and is inert unless `DASH_PASSWORD` is set, so local development keeps working unchanged. Read routes get a session-cookie gate; write routes keep the existing `X-Token`. The dashboard gains a PWA manifest, icons, and a service worker. A `deploy/` kit plus `docs/deploying.md` cover the Oracle VM, Caddy, and systemd.

**Tech Stack:** FastAPI, SQLite, pytest + httpx (`TestClient`), python-multipart (HTML form login), Caddy, systemd, Ubuntu on Oracle Cloud always-free.

**Spec:** [2026-08-20-cloud-hosting-and-pwa-design.md](../specs/2026-08-20-cloud-hosting-and-pwa-design.md)

---

## File Structure

| File | Responsibility |
|---|---|
| `server/auth.py` (new) | Password check, cookie signing/verification, secret persistence, rate limiting, login page HTML. No FastAPI imports — pure logic, easy to unit test. |
| `server/app.py` (modify) | Wires auth into routes; adds `/login`, `/logout`, `/healthz`, `/sw.js`, `/manifest.webmanifest`. |
| `server/static/index.html` (modify) | PWA meta tags; 401-aware fetch helper. |
| `server/static/manifest.webmanifest` (new) | PWA metadata. |
| `server/static/sw.js` (new) | Service worker. Never caches `/api/*`. |
| `server/static/icons/*.png` (new) | 192/512/180 app icons. |
| `tools/make_icons.py` (new) | Regenerates the icons; pure stdlib, no Pillow. |
| `server/tests/` (new) | conftest + auth unit tests + route integration tests. |
| `deploy/` (new) | `Caddyfile`, `tracker.service`, `tracker.env.example`. |
| `docs/deploying.md` (new) | Oracle + Caddy + systemd + iPhone walkthrough. |

---

### Task 1: Session token signing (pure logic)

**Files:**
- Create: `server/auth.py`
- Create: `server/tests/conftest.py`
- Create: `server/tests/test_auth_unit.py`
- Create: `server/requirements-dev.txt`

- [ ] **Step 1: Add dev dependencies**

Create `server/requirements-dev.txt`:

```
-r requirements.txt
pytest>=8.0
httpx>=0.27
```

Install: `python -m pip install -r server/requirements-dev.txt`

- [ ] **Step 2: Create the test path shim**

Create `server/tests/conftest.py`:

```python
"""Test setup. Tests import the server modules directly, so the server
directory has to be importable regardless of where pytest is invoked from."""

import sys
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER_DIR))
```

- [ ] **Step 3: Write the failing test**

Create `server/tests/test_auth_unit.py`:

```python
import auth


def test_token_roundtrip_validates():
    secret = b"k" * 32
    token = auth.make_token(secret, expiry=2000)
    assert auth.valid_token(secret, token, now=1000)


def test_expired_token_rejected():
    secret = b"k" * 32
    token = auth.make_token(secret, expiry=500)
    assert not auth.valid_token(secret, token, now=1000)


def test_token_from_other_secret_rejected():
    token = auth.make_token(b"a" * 32, expiry=2000)
    assert not auth.valid_token(b"b" * 32, token, now=1000)


def test_tampered_expiry_rejected():
    secret = b"k" * 32
    token = auth.make_token(secret, expiry=500)
    forged = "9999." + token.split(".", 1)[1]
    assert not auth.valid_token(secret, forged, now=1000)


def test_malformed_tokens_rejected():
    secret = b"k" * 32
    for bad in ["", "nonsense", "123", "abc.def", None]:
        assert not auth.valid_token(secret, bad, now=1000)
```

- [ ] **Step 4: Run it and watch it fail**

Run: `python -m pytest server/tests/test_auth_unit.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'auth'`

- [ ] **Step 5: Write the minimal implementation**

Create `server/auth.py`:

```python
"""Password gate for the dashboard's read routes.

Everything here is inert unless DASH_PASSWORD is set, so the default
localhost setup behaves exactly as it did before this module existed.
Deliberately free of FastAPI imports: it is plain logic, unit-testable
without spinning up an app.
"""

import hashlib
import hmac
import os
import time

COOKIE_NAME = "tracker_session"
SESSION_DAYS = 180
SESSION_SECONDS = SESSION_DAYS * 86400


def make_token(secret: bytes, expiry: int) -> str:
    """Signed session value: '<unix-expiry>.<hmac of that expiry>'."""
    sig = hmac.new(secret, str(expiry).encode(), hashlib.sha256).hexdigest()
    return f"{expiry}.{sig}"


def valid_token(secret: bytes, token, now: int | None = None) -> bool:
    now = int(time.time()) if now is None else now
    if not isinstance(token, str):
        return False
    try:
        expiry = int(token.split(".", 1)[0])
    except (ValueError, IndexError):
        return False
    if expiry < now:
        return False
    # Comparing the whole "expiry.sig" string in constant time also proves
    # the expiry half was not tampered with.
    return hmac.compare_digest(make_token(secret, expiry), token)
```

- [ ] **Step 6: Run it and watch it pass**

Run: `python -m pytest server/tests/test_auth_unit.py -v`
Expected: PASS, 5 passed

- [ ] **Step 7: Commit**

```bash
git add server/auth.py server/tests server/requirements-dev.txt
git commit -m "Add signed session tokens for dashboard auth"
```

---

### Task 2: Password check and secret persistence

**Files:**
- Modify: `server/auth.py`
- Modify: `server/tests/test_auth_unit.py`

- [ ] **Step 1: Write the failing test**

Append to `server/tests/test_auth_unit.py`:

```python
def test_disabled_when_no_password(monkeypatch):
    monkeypatch.delenv("DASH_PASSWORD", raising=False)
    assert not auth.enabled()


def test_enabled_with_password(monkeypatch):
    monkeypatch.setenv("DASH_PASSWORD", "hunter2")
    assert auth.enabled()
    assert auth.password_ok("hunter2")
    assert not auth.password_ok("wrong")
    assert not auth.password_ok("")


def test_secret_from_env_wins(monkeypatch, tmp_path):
    monkeypatch.setenv("SESSION_SECRET", "from-env")
    assert auth.load_secret(str(tmp_path / "tracker.db")) == b"from-env"


def test_secret_generated_and_reused(monkeypatch, tmp_path):
    """A restart must not log every phone out, so the generated key persists."""
    monkeypatch.delenv("SESSION_SECRET", raising=False)
    db = str(tmp_path / "tracker.db")
    first = auth.load_secret(db)
    assert len(first) == 32
    assert auth.load_secret(db) == first
```

- [ ] **Step 2: Run and watch it fail**

Run: `python -m pytest server/tests/test_auth_unit.py -v`
Expected: FAIL — `AttributeError: module 'auth' has no attribute 'enabled'`

- [ ] **Step 3: Implement**

Add to `server/auth.py` (imports `secrets` and `Path` go at the top with the others):

```python
import secrets
from pathlib import Path


def password() -> str:
    return os.environ.get("DASH_PASSWORD", "")


def enabled() -> bool:
    """Auth is opt-in: no DASH_PASSWORD means the old open behaviour."""
    return bool(password())


def password_ok(supplied) -> bool:
    if not isinstance(supplied, str) or not supplied:
        return False
    return hmac.compare_digest(supplied, password())


def load_secret(db_path: str) -> bytes:
    """Cookie signing key. SESSION_SECRET wins; otherwise generate one and
    persist it beside the database so restarts keep sessions alive."""
    env = os.environ.get("SESSION_SECRET")
    if env:
        return env.encode()
    path = Path(db_path).parent / ".session_secret"
    if path.exists():
        return path.read_bytes()
    key = secrets.token_bytes(32)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(key)
    return key
```

- [ ] **Step 4: Run and watch it pass**

Run: `python -m pytest server/tests/test_auth_unit.py -v`
Expected: PASS, 9 passed

- [ ] **Step 5: Commit**

```bash
git add server/auth.py server/tests/test_auth_unit.py
git commit -m "Add password check and persisted session secret"
```

---

### Task 3: Login rate limiting

**Files:**
- Modify: `server/auth.py`
- Modify: `server/tests/test_auth_unit.py`

- [ ] **Step 1: Write the failing test**

Append to `server/tests/test_auth_unit.py`:

```python
def test_rate_limit_trips_after_max_attempts():
    auth.reset_attempts()
    ip = "10.0.0.1"
    for _ in range(auth.MAX_ATTEMPTS):
        assert not auth.rate_limited(ip, now=1000.0)
        auth.record_failure(ip, now=1000.0)
    assert auth.rate_limited(ip, now=1000.0)


def test_rate_limit_expires_after_window():
    auth.reset_attempts()
    ip = "10.0.0.2"
    for _ in range(auth.MAX_ATTEMPTS):
        auth.record_failure(ip, now=1000.0)
    assert auth.rate_limited(ip, now=1000.0)
    later = 1000.0 + auth.WINDOW_SECONDS + 1
    assert not auth.rate_limited(ip, now=later)


def test_rate_limit_is_per_ip():
    auth.reset_attempts()
    for _ in range(auth.MAX_ATTEMPTS):
        auth.record_failure("10.0.0.3", now=1000.0)
    assert auth.rate_limited("10.0.0.3", now=1000.0)
    assert not auth.rate_limited("10.0.0.4", now=1000.0)
```

- [ ] **Step 2: Run and watch it fail**

Run: `python -m pytest server/tests/test_auth_unit.py -v`
Expected: FAIL — `AttributeError: module 'auth' has no attribute 'reset_attempts'`

- [ ] **Step 3: Implement**

Add to `server/auth.py`:

```python
MAX_ATTEMPTS = 10
WINDOW_SECONDS = 15 * 60

# ip -> list of failure timestamps. In-memory is right for a single-user
# deployment; a restart clearing it is not worth a table.
_attempts: dict[str, list[float]] = {}


def reset_attempts() -> None:
    _attempts.clear()


def rate_limited(ip: str, now: float | None = None) -> bool:
    now = time.time() if now is None else now
    hits = [t for t in _attempts.get(ip, []) if now - t < WINDOW_SECONDS]
    _attempts[ip] = hits
    return len(hits) >= MAX_ATTEMPTS


def record_failure(ip: str, now: float | None = None) -> None:
    now = time.time() if now is None else now
    _attempts.setdefault(ip, []).append(now)
```

- [ ] **Step 4: Run and watch it pass**

Run: `python -m pytest server/tests/test_auth_unit.py -v`
Expected: PASS, 12 passed

- [ ] **Step 5: Commit**

```bash
git add server/auth.py server/tests/test_auth_unit.py
git commit -m "Rate-limit failed dashboard logins per IP"
```

---

### Task 4: Login page HTML

**Files:**
- Modify: `server/auth.py`
- Modify: `server/tests/test_auth_unit.py`

- [ ] **Step 1: Write the failing test**

Append to `server/tests/test_auth_unit.py`:

```python
def test_login_page_renders_form():
    html = auth.login_page_html()
    assert '<form method="post" action="/login"' in html
    assert 'type="password"' in html
    assert "name=\"password\"" in html


def test_login_page_shows_error_when_given():
    assert "Incorrect password." in auth.login_page_html("Incorrect password.")
    assert "Incorrect password." not in auth.login_page_html()
```

- [ ] **Step 2: Run and watch it fail**

Run: `python -m pytest server/tests/test_auth_unit.py -v`
Expected: FAIL — `AttributeError: module 'auth' has no attribute 'login_page_html'`

- [ ] **Step 3: Implement**

Add to `server/auth.py`:

```python
import html as _html

_LOGIN_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Tracker</title>
<style>
  :root {{ --page:#f9f9f7; --surface:#fcfcfb; --ink:#0b0b0b;
           --muted:#898781; --hairline:#e1e0d9; --critical:#d03b3b; }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --page:#0d0d0d; --surface:#1a1a19; --ink:#fff;
             --hairline:#2c2c2a; }}
  }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; min-height:100vh; display:flex; align-items:center;
          justify-content:center; background:var(--page); color:var(--ink);
          font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }}
  form {{ background:var(--surface); border:1px solid var(--hairline);
          border-radius:14px; padding:28px; width:min(92vw,340px); }}
  h1 {{ margin:0 0 4px; font-size:19px; }}
  p {{ margin:0 0 18px; color:var(--muted); font-size:13px; }}
  input {{ width:100%; padding:11px 12px; font-size:16px; color:var(--ink);
           background:transparent; border:1px solid var(--hairline);
           border-radius:9px; }}
  button {{ width:100%; margin-top:10px; padding:11px; font-size:15px;
            font-weight:600; color:var(--page); background:var(--ink);
            border:0; border-radius:9px; cursor:pointer; }}
  .err {{ margin:0 0 12px; color:var(--critical); font-size:13px; }}
</style>
</head>
<body>
<form method="post" action="/login">
  <h1>Tracker</h1>
  <p>Enter the dashboard password.</p>
  {error}
  <input type="password" name="password" placeholder="Password"
         autocomplete="current-password" autofocus>
  <button type="submit">Sign in</button>
</form>
</body>
</html>
"""


def login_page_html(error: str = "") -> str:
    """Login page. `error` is escaped; the page never says whether a
    password merely exists, so there is nothing to enumerate."""
    block = f'<p class="err">{_html.escape(error)}</p>' if error else ""
    return _LOGIN_PAGE.format(error=block)
```

Note the doubled braces in the CSS: the template goes through `str.format`, so literal `{` must be written `{{`.

- [ ] **Step 4: Run and watch it pass**

Run: `python -m pytest server/tests/test_auth_unit.py -v`
Expected: PASS, 14 passed

- [ ] **Step 5: Commit**

```bash
git add server/auth.py server/tests/test_auth_unit.py
git commit -m "Add login page markup"
```

---

### Task 5: Wire auth into the app

**Files:**
- Modify: `server/app.py`
- Modify: `server/tests/conftest.py`
- Create: `server/tests/test_routes.py`
- Modify: `server/requirements.txt`

- [ ] **Step 1: Add the form-parsing dependency**

FastAPI needs `python-multipart` to read an HTML form POST. Update `server/requirements.txt`:

```
fastapi>=0.115
uvicorn>=0.30
python-multipart>=0.0.9
```

Install: `python -m pip install -r server/requirements.txt`

- [ ] **Step 2: Add the client fixture**

Replace `server/tests/conftest.py` with:

```python
"""Test setup. Tests import the server modules directly, so the server
directory has to be importable regardless of where pytest is invoked from."""

import importlib
import sys
from pathlib import Path

import pytest

SERVER_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER_DIR))


@pytest.fixture
def make_client(tmp_path, monkeypatch):
    """Builds a TestClient against a freshly reloaded app.

    app.py reads its configuration at import time, so each test that wants
    different environment settings needs the module reloaded.
    """
    def _make(**env):
        monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
        monkeypatch.setenv("API_TOKEN", "test-token")
        monkeypatch.setenv("COOKIE_SECURE", "0")  # TestClient speaks http
        for key in ("DASH_PASSWORD", "SESSION_SECRET"):
            monkeypatch.delenv(key, raising=False)
        for key, value in env.items():
            monkeypatch.setenv(key, value)

        import auth
        importlib.reload(auth)
        auth.reset_attempts()
        import app as app_module
        importlib.reload(app_module)

        from fastapi.testclient import TestClient
        return TestClient(app_module.app)
    return _make
```

- [ ] **Step 3: Write the failing tests**

Create `server/tests/test_routes.py`:

```python
PW = {"DASH_PASSWORD": "hunter2"}


def login(client, password="hunter2"):
    return client.post("/login", data={"password": password},
                       follow_redirects=False)


def test_api_devices_requires_session(make_client):
    client = make_client(**PW)
    assert client.get("/api/devices").status_code == 401


def test_dashboard_redirects_to_login(make_client):
    client = make_client(**PW)
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "/login"


def test_login_then_read(make_client):
    client = make_client(**PW)
    r = login(client)
    assert r.status_code == 303
    assert client.get("/api/devices").status_code == 200
    assert client.get("/", follow_redirects=False).status_code == 200


def test_wrong_password_rejected(make_client):
    client = make_client(**PW)
    r = login(client, "wrong")
    assert r.status_code == 401
    assert client.get("/api/devices").status_code == 401


def test_rate_limit_after_ten_failures(make_client):
    client = make_client(**PW)
    for _ in range(10):
        login(client, "wrong")
    assert login(client, "wrong").status_code == 429
    # Correct password is refused too while the window is open.
    assert login(client).status_code == 429


def test_logout_clears_session(make_client):
    client = make_client(**PW)
    login(client)
    assert client.get("/api/devices").status_code == 200
    client.get("/logout", follow_redirects=False)
    assert client.get("/api/devices").status_code == 401


def test_sighting_uses_token_not_session(make_client):
    """Listeners must keep working with no session at all."""
    client = make_client(**PW)
    body = {"listener": "home",
            "tags": [{"mac": "C6:8C:B5:57:0E:16", "rssi": -60}]}
    r = client.post("/api/sighting", json=body,
                    headers={"X-Token": "test-token"})
    assert r.status_code == 200
    assert r.json()["recognized"] == ["keyring"]
    assert client.post("/api/sighting", json=body,
                       headers={"X-Token": "nope"}).status_code == 401


def test_healthz_is_public(make_client):
    client = make_client(**PW)
    assert client.get("/healthz").status_code == 200


def test_no_password_keeps_everything_open(make_client):
    """Backward compatibility: the existing localhost setup is untouched."""
    client = make_client()
    assert client.get("/api/devices").status_code == 200
    assert client.get("/", follow_redirects=False).status_code == 200
```

- [ ] **Step 4: Run and watch them fail**

Run: `python -m pytest server/tests/test_routes.py -v`
Expected: FAIL — `/api/devices` returns 200 instead of 401; `/login` returns 404.

- [ ] **Step 5: Implement in `server/app.py`**

Change the imports at `server/app.py:13-15` to:

```python
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import (FileResponse, HTMLResponse, JSONResponse,
                               RedirectResponse)
from fastapi.staticfiles import StaticFiles

import auth
```

Add after the `API_TOKEN`/`DB_PATH`/`STATIC_DIR` block (around `server/app.py:19`):

```python
SESSION_SECRET = auth.load_secret(DB_PATH)
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "1") != "0"
```

Add this dependency just above the route definitions (before `@app.post("/api/ping")`):

```python
def require_session(request: Request):
    """Gate for routes that expose location data. A no-op when auth is off."""
    if not auth.enabled():
        return
    token = request.cookies.get(auth.COOKIE_NAME, "")
    if not auth.valid_token(SESSION_SECRET, token):
        raise HTTPException(401, "login required")
```

Add `dependencies=[Depends(require_session)]` to the two read routes:

```python
@app.get("/api/devices", dependencies=[Depends(require_session)])
def devices():
```

```python
@app.get("/api/devices/{device}/history",
         dependencies=[Depends(require_session)])
def history(device: str, hours: float = 24):
```

Replace the `index` route at `server/app.py:167-169` with:

```python
@app.get("/")
def index(request: Request):
    if auth.enabled() and not auth.valid_token(
            SESSION_SECRET, request.cookies.get(auth.COOKIE_NAME, "")):
        return RedirectResponse("/login", status_code=302)
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.get("/login")
def login_page():
    return HTMLResponse(auth.login_page_html())


@app.post("/login")
async def login(request: Request):
    ip = request.client.host if request.client else "?"
    if auth.rate_limited(ip):
        return HTMLResponse(
            auth.login_page_html("Too many attempts. Try again in 15 minutes."),
            status_code=429)
    form = await request.form()
    if not auth.password_ok(str(form.get("password", ""))):
        auth.record_failure(ip)
        return HTMLResponse(auth.login_page_html("Incorrect password."),
                            status_code=401)
    expiry = int(time.time()) + auth.SESSION_SECONDS
    resp = RedirectResponse("/", status_code=303)
    resp.set_cookie(auth.COOKIE_NAME, auth.make_token(SESSION_SECRET, expiry),
                    max_age=auth.SESSION_SECONDS, httponly=True,
                    secure=COOKIE_SECURE, samesite="lax")
    return resp


@app.get("/logout")
def logout():
    resp = RedirectResponse("/login", status_code=302)
    resp.delete_cookie(auth.COOKIE_NAME)
    return resp
```

- [ ] **Step 6: Run and watch them pass**

Run: `python -m pytest server/tests -v`
Expected: PASS, 23 passed

- [ ] **Step 7: Commit**

```bash
git add server/app.py server/tests server/requirements.txt
git commit -m "Gate dashboard reads behind a password session"
```

---

### Task 6: Dashboard handles 401

**Files:**
- Modify: `server/static/index.html:163`, `:235-236`, `:275`

- [ ] **Step 1: Add the fetch helper**

In `server/static/index.html`, immediately after the opening `<script>` tag at line 122, add:

```javascript
// Session can expire while the page is open (or while it sits in the
// iOS app switcher for weeks). Bounce to the login page instead of
// rendering an error.
async function api(path) {
  const r = await fetch(path);
  if (r.status === 401) { location.href = "/login"; throw new Error("401"); }
  return r.json();
}
```

- [ ] **Step 2: Use it at all three call sites**

Line 163 becomes:

```javascript
  try { devs = await api("/api/devices"); }
```

Lines 235-236 become:

```javascript
      const hist = await api(
        `/api/devices/${encodeURIComponent(d.device)}/history?hours=${hours}`);
```

Line 275 becomes:

```javascript
  try { devs = await api("/api/devices"); } catch { return; }
```

- [ ] **Step 3: Verify manually**

```bash
cd server && DASH_PASSWORD=test COOKIE_SECURE=0 python -m uvicorn app:app --port 8000
```

Open `http://127.0.0.1:8000` — expect a redirect to the login form; sign in with `test`; expect the dashboard. Then delete the `tracker_session` cookie in devtools and wait for the refresh tick — expect a bounce back to `/login`.

- [ ] **Step 4: Commit**

```bash
git add server/static/index.html
git commit -m "Send the dashboard to the login page on 401"
```

---

### Task 7: App icons

**Files:**
- Create: `tools/make_icons.py`
- Create: `server/static/icons/icon-192.png`, `icon-512.png`, `icon-180.png`

- [ ] **Step 1: Write the generator**

Create `tools/make_icons.py`:

```python
"""Generate the PWA app icons — a beacon mark: solid dot with two rings.

Pure stdlib (no Pillow) so it runs anywhere. Rerun after changing colours:
  python tools/make_icons.py
"""

import struct
import zlib
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "server" / "static" / "icons"
BG = (18, 33, 46)       # deep navy
FG = (255, 255, 255)

# Ring geometry as fractions of the icon's width, all inside the middle 80%
# so a maskable icon never crops the mark.
DOT = 0.10
RINGS = ((0.22, 0.26), (0.34, 0.38))


def pixels(size):
    c = (size - 1) / 2
    for y in range(size):
        row = []
        for x in range(size):
            d = ((x - c) ** 2 + (y - c) ** 2) ** 0.5 / size
            on = d <= DOT or any(lo <= d <= hi for lo, hi in RINGS)
            row.append(FG if on else BG)
        yield row


def write_png(path, size):
    raw = b"".join(b"\x00" + bytes(v for px in row for v in px)
                   for row in pixels(size))

    def chunk(tag, data):
        body = tag + data
        return (struct.pack(">I", len(data)) + body
                + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)  # 8-bit RGB
    path.write_bytes(b"\x89PNG\r\n\x1a\n"
                     + chunk(b"IHDR", ihdr)
                     + chunk(b"IDAT", zlib.compress(raw, 9))
                     + chunk(b"IEND", b""))
    print(f"wrote {path.name} ({size}x{size})")


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for size in (180, 192, 512):
        write_png(OUT / f"icon-{size}.png", size)
```

- [ ] **Step 2: Generate and verify**

Run: `python tools/make_icons.py`
Expected: three "wrote icon-NNN.png" lines.

Verify they are real PNGs of the right size:

```bash
python -c "import struct,pathlib; [print(p.name, struct.unpack('>II', p.read_bytes()[16:24])) for p in sorted(pathlib.Path('server/static/icons').glob('*.png'))]"
```
Expected: `icon-180.png (180, 180)`, `icon-192.png (192, 192)`, `icon-512.png (512, 512)`

Open `server/static/icons/icon-512.png` and confirm it renders as a white beacon mark on navy.

- [ ] **Step 3: Commit**

```bash
git add tools/make_icons.py server/static/icons
git commit -m "Add generated PWA app icons"
```

---

### Task 8: Manifest, meta tags, and their routes

**Files:**
- Create: `server/static/manifest.webmanifest`
- Modify: `server/static/index.html:3-8`
- Modify: `server/app.py`
- Modify: `server/tests/test_routes.py`

- [ ] **Step 1: Write the failing test**

Append to `server/tests/test_routes.py`:

```python
def test_pwa_assets_are_public(make_client):
    """The phone fetches these before it has a session."""
    client = make_client(**PW)
    m = client.get("/manifest.webmanifest")
    assert m.status_code == 200
    assert m.json()["display"] == "standalone"
    assert client.get("/static/icons/icon-192.png").status_code == 200
```

- [ ] **Step 2: Run and watch it fail**

Run: `python -m pytest server/tests/test_routes.py::test_pwa_assets_are_public -v`
Expected: FAIL — 404 on `/manifest.webmanifest`

- [ ] **Step 3: Create the manifest**

Create `server/static/manifest.webmanifest`:

```json
{
  "name": "Tracker",
  "short_name": "Tracker",
  "description": "Self-hosted tag tracker",
  "start_url": "/",
  "scope": "/",
  "display": "standalone",
  "background_color": "#12212e",
  "theme_color": "#12212e",
  "icons": [
    {"src": "/static/icons/icon-192.png", "sizes": "192x192", "type": "image/png"},
    {"src": "/static/icons/icon-512.png", "sizes": "512x512", "type": "image/png"},
    {"src": "/static/icons/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"}
  ]
}
```

- [ ] **Step 4: Serve it from the app**

Add to `server/app.py` next to the other public routes:

```python
@app.get("/manifest.webmanifest")
def manifest():
    return FileResponse(STATIC_DIR / "manifest.webmanifest",
                        media_type="application/manifest+json")
```

- [ ] **Step 5: Add the iOS meta tags**

In `server/static/index.html`, after the `<title>Tracker</title>` line (line 6), add:

```html
<link rel="manifest" href="/manifest.webmanifest">
<meta name="theme-color" content="#12212e">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="Tracker">
<link rel="apple-touch-icon" href="/static/icons/icon-180.png">
```

- [ ] **Step 6: Run and watch it pass**

Run: `python -m pytest server/tests -v`
Expected: PASS, 24 passed

- [ ] **Step 7: Commit**

```bash
git add server/static/manifest.webmanifest server/static/index.html server/app.py server/tests/test_routes.py
git commit -m "Make the dashboard installable as a PWA"
```

---

### Task 9: Service worker

**Files:**
- Create: `server/static/sw.js`
- Modify: `server/app.py`
- Modify: `server/static/index.html`
- Modify: `server/tests/test_routes.py`

- [ ] **Step 1: Write the failing test**

Append to `server/tests/test_routes.py`:

```python
def test_service_worker_served_at_root(make_client):
    """Scope: a worker served from /static could only control /static."""
    client = make_client(**PW)
    r = client.get("/sw.js")
    assert r.status_code == 200
    assert "javascript" in r.headers["content-type"]
```

- [ ] **Step 2: Run and watch it fail**

Run: `python -m pytest server/tests/test_routes.py::test_service_worker_served_at_root -v`
Expected: FAIL — 404

- [ ] **Step 3: Write the worker**

Create `server/static/sw.js`:

```javascript
// Minimal worker: it exists to make the dashboard installable and to let
// the shell open instantly. Location data is never cached — a stale
// position is worse than no position — so /api is always network-only.
const CACHE = "tracker-shell-v1";
const SHELL = [
  "/static/icons/icon-192.png",
  "/static/icons/icon-512.png",
  "/manifest.webmanifest",
];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)));
  self.skipWaiting();
});

self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((keys) => Promise.all(
    keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))));
  self.clients.claim();
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  const cacheable = e.request.method === "GET"
    && url.origin === location.origin
    && !url.pathname.startsWith("/api/");
  if (!cacheable) return;  // fall through to the network
  e.respondWith(
    caches.match(e.request).then((hit) => hit || fetch(e.request))
  );
});
```

- [ ] **Step 4: Serve it at root scope**

Add to `server/app.py`:

```python
@app.get("/sw.js")
def service_worker():
    return FileResponse(STATIC_DIR / "sw.js",
                        media_type="application/javascript")
```

- [ ] **Step 5: Register it**

In `server/static/index.html`, add just after the `api()` helper added in Task 6:

```javascript
if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").catch(() => {});
}
```

- [ ] **Step 6: Run and watch it pass**

Run: `python -m pytest server/tests -v`
Expected: PASS, 25 passed

- [ ] **Step 7: Commit**

```bash
git add server/static/sw.js server/static/index.html server/app.py server/tests/test_routes.py
git commit -m "Add service worker for offline shell and installability"
```

---

### Task 10: Deployment kit

**Files:**
- Create: `deploy/Caddyfile`, `deploy/tracker.service`, `deploy/tracker.env.example`
- Modify: `.gitignore`

- [ ] **Step 1: Caddyfile**

Create `deploy/Caddyfile`:

```
# Replace YOUR-HOST with your DuckDNS name, e.g. yash-tracker.duckdns.org
# Caddy obtains and renews the Let's Encrypt certificate automatically.
YOUR-HOST {
	encode gzip
	reverse_proxy 127.0.0.1:8000
}
```

- [ ] **Step 2: systemd unit**

Create `deploy/tracker.service`:

```ini
[Unit]
Description=custom_airtag tracker server
After=network.target

[Service]
User=tracker
Group=tracker
WorkingDirectory=/opt/custom_airtag/server
EnvironmentFile=/etc/tracker.env
ExecStart=/opt/custom_airtag/.venv/bin/uvicorn app:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

Note `--host 127.0.0.1`: only Caddy should reach uvicorn, never the internet directly.

- [ ] **Step 3: env template**

Create `deploy/tracker.env.example`:

```bash
# Copy to /etc/tracker.env on the server, fill in, then:
#   sudo chmod 600 /etc/tracker.env && sudo chown tracker:tracker /etc/tracker.env

# Shared secret for listeners posting sightings. Generate a NEW one for the
# cloud; the LAN token was never meant to cross the internet:
#   python -c "import secrets; print(secrets.token_urlsafe(32))"
API_TOKEN=

# Dashboard password. Long and random; you type it once per device.
DASH_PASSWORD=

# Cookie signing key. Leave blank to have one generated and persisted next
# to the database. Set it explicitly if you ever run more than one process.
SESSION_SECRET=

DB_PATH=/var/lib/tracker/tracker.db
```

- [ ] **Step 4: Keep the real env file out of git**

Append to `.gitignore`:

```
# Server env file (tokens, dashboard password) — commit the .example only
deploy/tracker.env
```

- [ ] **Step 5: Commit**

```bash
git add deploy .gitignore
git commit -m "Add Caddy, systemd, and env templates for cloud deploy"
```

---

### Task 11: Deployment documentation

**Files:**
- Create: `docs/deploying.md`
- Modify: `README.md`

- [ ] **Step 1: Write `docs/deploying.md`**

It must cover, in order, with copy-pasteable commands:

1. **Oracle VM** — always-free `VM.Standard.A1.Flex` (fallback
   `VM.Standard.E2.1.Micro`), Ubuntu 24.04, save the SSH key, reserve the
   public IP so it survives a reboot.
2. **Both firewalls.** The VCN security list needs ingress on 80 and 443,
   *and* the instance's own iptables must be opened:
   ```bash
   sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
   sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
   sudo netfilter-persistent save
   ```
   Call out that missing the second one presents as Caddy failing to get a
   certificate, which sends people hunting the wrong problem.
3. **DuckDNS** — register a subdomain, point it at the reserved IP.
4. **Install**:
   ```bash
   sudo apt update && sudo apt install -y python3-venv git
   sudo useradd -r -m -d /var/lib/tracker tracker
   sudo git clone https://github.com/yashpatel1314/custom_airtag /opt/custom_airtag
   sudo python3 -m venv /opt/custom_airtag/.venv
   sudo /opt/custom_airtag/.venv/bin/pip install -r /opt/custom_airtag/server/requirements.txt
   sudo mkdir -p /var/lib/tracker && sudo chown tracker:tracker /var/lib/tracker
   ```
5. **Configure** — copy `deploy/tracker.env.example` to `/etc/tracker.env`,
   fill it, `chmod 600`, `chown tracker:tracker`.
6. **Services**:
   ```bash
   sudo cp /opt/custom_airtag/deploy/tracker.service /etc/systemd/system/
   sudo systemctl enable --now tracker
   sudo apt install -y caddy   # per caddyserver.com/docs/install
   sudo cp /opt/custom_airtag/deploy/Caddyfile /etc/caddy/Caddyfile
   sudo sed -i "s/YOUR-HOST/<your>.duckdns.org/" /etc/caddy/Caddyfile
   sudo systemctl reload caddy
   ```
7. **Verify** — `curl https://<host>/healthz` returns `{"ok":true}`;
   opening the host in a browser shows the login page.
8. **Point the home listener at it** — edit `server/start-listener.bat`,
   replacing the server URL with `https://<host>` and the token with the
   cloud `API_TOKEN`.
9. **Install on iPhone** — Safari, Share, Add to Home Screen. Note that
   Safari is required (Chrome on iOS cannot install PWAs), and mention the
   Android/Chrome "Install app" prompt for completeness.
10. **Troubleshooting table** — certificate not issued (firewall layer 2),
    502 from Caddy (`systemctl status tracker`, `journalctl -u tracker`),
    login loops (cookie blocked because `COOKIE_SECURE=1` while browsing
    over plain http), listener posting 401 (token mismatch).

- [ ] **Step 2: Link it from the README**

In `README.md`, under the Build C steps, add a line after the server step:

```markdown
To reach the dashboard from your phone anywhere, deploy it to a free cloud
VM with HTTPS and a password: [docs/deploying.md](docs/deploying.md).
```

- [ ] **Step 3: Commit**

```bash
git add docs/deploying.md README.md
git commit -m "Document cloud deployment and iPhone install"
```

---

### Task 12: Full local verification

**Files:** none (verification only)

- [ ] **Step 1: Whole suite**

Run: `python -m pytest server/tests -v`
Expected: PASS, 25 passed

- [ ] **Step 2: Confirm the old behaviour is genuinely untouched**

```bash
cd server && API_TOKEN=e2e python -m uvicorn app:app --port 8000
```
In another shell: `curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8000/api/devices`
Expected: `200` — no password configured means no gate, exactly as before.

- [ ] **Step 3: Confirm the gate with a password**

```bash
cd server && API_TOKEN=e2e DASH_PASSWORD=test COOKIE_SECURE=0 python -m uvicorn app:app --port 8000
```
```bash
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8000/api/devices          # 401
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8000/healthz              # 200
curl -s -c /tmp/j -o /dev/null -w '%{http_code}\n' -d 'password=test' http://127.0.0.1:8000/login   # 303
curl -s -b /tmp/j -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8000/api/devices # 200
```

- [ ] **Step 4: End-to-end with the real tag**

With the password-protected server running, start the listener
(`python listener.py --token e2e`) and confirm `keyring` appears via the
authenticated `/api/devices`. This proves listeners still post while reads
are gated.

- [ ] **Step 5: Commit any fixes, then push**

```bash
git push origin main
```

---

## Deferred (Phase 3, not in this plan)

- ESP32 listener HTTPS support (`WiFiClientSecure::setCACert` with ISRG
  Root X1). No node is deployed, so this is speculative until one is.
- Bringing `tag-02` and `tag-03` onto the cloud dashboard. Their MACs are
  already in `server/tags.json`, so tracking needs no reflash; the
  outstanding blocker is that `findmy/keys/` is empty on this PC, which
  prevents reflashing them for battery percentages.
