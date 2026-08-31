"""Password gate for the dashboard's read routes.

Everything here is inert unless DASH_PASSWORD is set, so the default
localhost setup behaves exactly as it did before this module existed.
Deliberately free of FastAPI imports: it is plain logic, unit-testable
without spinning up an app.
"""

import hashlib
import hmac
import html as _html
import os
import secrets
import time
from pathlib import Path

COOKIE_NAME = "tracker_session"
SESSION_DAYS = 180
SESSION_SECONDS = SESSION_DAYS * 86400

MAX_ATTEMPTS = 10
WINDOW_SECONDS = 15 * 60


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


_LOGIN_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Tracker</title>
<meta name="theme-color" content="#12212e">
<link rel="apple-touch-icon" href="/static/icons/icon-180.png">
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
