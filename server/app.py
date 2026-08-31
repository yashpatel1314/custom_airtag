"""Self-hosted tracker backend: receives pings from the tag over plain HTTP,
stores them in SQLite, serves the dashboard and a small JSON API.

Run:  API_TOKEN=<secret> uvicorn app:app --host 0.0.0.0 --port 8000
Everything lives in one process; the DB is a single file (tracker.db).
"""

import os
import sqlite3
import time
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import (FileResponse, HTMLResponse, JSONResponse,
                               RedirectResponse)
from fastapi.staticfiles import StaticFiles

import auth

API_TOKEN = os.environ.get("API_TOKEN", "change-me-long-random-string")
DB_PATH = os.environ.get("DB_PATH", str(Path(__file__).parent / "tracker.db"))
STATIC_DIR = Path(__file__).parent / "static"

# Dashboard session signing key, and whether cookies require HTTPS.
# COOKIE_SECURE=0 is only for local http testing.
SESSION_SECRET = auth.load_secret(DB_PATH)
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "1") != "0"

import json

# BLE MAC -> friendly tag name, for listener-reported sightings.
TAGS_PATH = Path(__file__).parent / "tags.json"
TAG_NAMES = {}
if TAGS_PATH.exists():
    TAG_NAMES = {k.upper(): v for k, v in json.loads(TAGS_PATH.read_text()).items()}

# Zone/listener name -> fixed coordinates, so a listener that doesn't send its
# own lat/lon still gives its tags a map pin at the zone's landmark.
LANDMARKS_PATH = Path(__file__).parent / "landmarks.json"
LANDMARKS = {}
if LANDMARKS_PATH.exists():
    LANDMARKS = {k.lower(): v for k, v in json.loads(LANDMARKS_PATH.read_text()).items()}

app = FastAPI(title="custom-airtag")


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


with db() as conn:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS pings (
               id      INTEGER PRIMARY KEY AUTOINCREMENT,
               device  TEXT NOT NULL,
               ts      INTEGER NOT NULL,          -- unix seconds, server clock
               fix     INTEGER NOT NULL,
               lat     REAL, lon REAL, speed REAL, alt REAL, sats INTEGER,
               batt_mv INTEGER, csq INTEGER, boot INTEGER
           )"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_dev_ts ON pings(device, ts)")
    for col, typ in (("listener", "TEXT"), ("rssi", "INTEGER"),
                     ("batt_lvl", "TEXT"), ("batt_pct", "INTEGER")):
        try:
            conn.execute(f"ALTER TABLE pings ADD COLUMN {col} {typ}")
        except sqlite3.OperationalError:
            pass  # column already exists


def require_session(request: Request):
    """Gate for routes that expose location data. A no-op when auth is off."""
    if not auth.enabled():
        return
    token = request.cookies.get(auth.COOKIE_NAME, "")
    if not auth.valid_token(SESSION_SECRET, token):
        raise HTTPException(401, "login required")


@app.post("/api/ping")
async def ping(req: Request, x_token: str = Header(default="")):
    if x_token != API_TOKEN:
        raise HTTPException(401, "bad token")
    body = await req.json()
    if "id" not in body:
        raise HTTPException(400, "missing id")
    has_fix = bool(body.get("fix"))
    with db() as conn:
        conn.execute(
            "INSERT INTO pings (device, ts, fix, lat, lon, speed, alt, sats,"
            " batt_mv, csq, boot) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                str(body["id"])[:64],
                int(time.time()),
                int(has_fix),
                body.get("lat") if has_fix else None,
                body.get("lon") if has_fix else None,
                body.get("speed"),
                body.get("alt"),
                body.get("sats"),
                body.get("batt_mv"),
                body.get("csq"),
                body.get("boot"),
            ),
        )
    return {"ok": True}


@app.post("/api/sighting")
async def sighting(req: Request, x_token: str = Header(default="")):
    """Fixed BLE listener report: which tags it can hear right now.

    Body: {"listener": "home", "lat": 37.7, "lon": -122.4,
           "tags": [{"mac": "C6:8C:B5:57:0E:16", "rssi": -61}, ...]}
    lat/lon are the listener's position and may be omitted (e.g. car node);
    the tag is then shown by zone name with its last known map position.
    """
    if x_token != API_TOKEN:
        raise HTTPException(401, "bad token")
    body = await req.json()
    listener = str(body.get("listener", "?"))[:64]
    lat, lon = body.get("lat"), body.get("lon")
    # No explicit position? Fall back to this zone's landmark coordinates.
    if (lat is None or lon is None) and listener.lower() in LANDMARKS:
        lm = LANDMARKS[listener.lower()]
        lat, lon = lm.get("lat"), lm.get("lon")
    has_pos = lat is not None and lon is not None
    now = int(time.time())
    seen = []
    with db() as conn:
        for t in body.get("tags", []):
            name = TAG_NAMES.get(str(t.get("mac", "")).upper())
            if not name:
                continue  # not one of our tags
            conn.execute(
                "INSERT INTO pings (device, ts, fix, lat, lon, rssi, listener,"
                " batt_lvl, batt_pct) VALUES (?,?,?,?,?,?,?,?,?)",
                (name, now, int(has_pos), lat if has_pos else None,
                 lon if has_pos else None, t.get("rssi"), listener,
                 t.get("batt"), t.get("batt_pct")),
            )
            seen.append(name)
    return {"ok": True, "recognized": seen}


@app.get("/api/devices", dependencies=[Depends(require_session)])
def devices():
    with db() as conn:
        rows = conn.execute(
            """SELECT p.* FROM pings p
               JOIN (SELECT device, MAX(id) AS mid FROM pings GROUP BY device) m
                 ON p.id = m.mid
               ORDER BY p.device"""
        ).fetchall()
        # Latest row per device may lack a fix; also fetch last known position.
        out = []
        for r in rows:
            d = dict(r)
            if not d["fix"]:
                last_fix = conn.execute(
                    "SELECT lat, lon, ts FROM pings WHERE device=? AND fix=1"
                    " ORDER BY ts DESC LIMIT 1",
                    (d["device"],),
                ).fetchone()
                d["last_fix"] = dict(last_fix) if last_fix else None
            out.append(d)
    return JSONResponse(out)


@app.get("/api/devices/{device}/history",
         dependencies=[Depends(require_session)])
def history(device: str, hours: float = 24):
    since = int(time.time() - hours * 3600)
    with db() as conn:
        rows = conn.execute(
            "SELECT ts, lat, lon, speed, batt_mv, csq FROM pings"
            " WHERE device=? AND fix=1 AND ts>=? ORDER BY ts",
            (device, since),
        ).fetchall()
    return JSONResponse([dict(r) for r in rows])


@app.get("/")
def index(request: Request):
    if auth.enabled() and not auth.valid_token(
            SESSION_SECRET, request.cookies.get(auth.COOKIE_NAME, "")):
        return RedirectResponse("/login", status_code=302)
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.get("/manifest.webmanifest")
def manifest():
    return FileResponse(STATIC_DIR / "manifest.webmanifest",
                        media_type="application/manifest+json")


@app.get("/sw.js")
def service_worker():
    # Served from the root so its scope covers the whole app; a worker at
    # /static/sw.js could only ever control /static.
    return FileResponse(STATIC_DIR / "sw.js",
                        media_type="application/javascript")


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


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
