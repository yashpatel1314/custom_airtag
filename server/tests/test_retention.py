"""Retention: the pings table otherwise grows forever (~0.5 GB/year for
three tags at a 15s interval), which matters on an SD card."""

import time


def insert(client, device, age_days):
    """Write one row directly, backdated, via the app's own connection."""
    import app
    ts = int(time.time()) - int(age_days * 86400)
    with app.db() as conn:
        conn.execute("INSERT INTO pings (device, ts, fix, listener)"
                     " VALUES (?,?,0,'home')", (device, ts))


def count(client):
    import app
    with app.db() as conn:
        return conn.execute("SELECT COUNT(*) FROM pings").fetchone()[0]


def test_prune_removes_only_old_rows(make_client):
    client = make_client(DASH_PASSWORD="pw", RETENTION_DAYS="90")
    import app
    insert(client, "keyring", age_days=200)
    insert(client, "keyring", age_days=91)
    insert(client, "keyring", age_days=10)
    insert(client, "keyring", age_days=0)
    assert count(client) == 4

    removed = app.prune_old()
    assert removed == 2
    assert count(client) == 2


def test_retention_disabled_by_default(make_client):
    """Existing installs must not silently lose history on upgrade."""
    client = make_client(DASH_PASSWORD="pw")
    import app
    assert app.RETENTION_DAYS == 0
    insert(client, "keyring", age_days=9999)
    assert app.prune_old() == 0
    assert count(client) == 1


def test_sighting_triggers_pruning(make_client):
    client = make_client(DASH_PASSWORD="pw", RETENTION_DAYS="30")
    import app
    insert(client, "keyring", age_days=400)
    assert count(client) == 1

    app._last_prune = 0.0   # force the once-an-hour guard to fire
    body = {"listener": "home",
            "tags": [{"mac": "D5:5A:2C:64:39:7A", "rssi": -60}]}
    client.post("/api/sighting", json=body, headers={"X-Token": "test-token"})
    # Old row pruned, the new sighting kept.
    assert count(client) == 1
    with app.db() as conn:
        age = conn.execute("SELECT MAX(ts) FROM pings").fetchone()[0]
    assert time.time() - age < 60
