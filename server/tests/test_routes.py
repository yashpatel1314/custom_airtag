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
            "tags": [{"mac": "D5:5A:2C:64:39:7A", "rssi": -60}]}
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
    """Backward compatibility: the localhost setup still works, but now it
    has to say so explicitly."""
    client = make_client(ALLOW_OPEN_DASHBOARD="1")
    assert client.get("/api/devices").status_code == 200
    assert client.get("/", follow_redirects=False).status_code == 200


def test_refuses_to_start_with_no_password_and_no_optin(make_client):
    """Fail closed: a blank DASH_PASSWORD must not silently publish
    everyone's location data to the internet."""
    import pytest
    with pytest.raises(RuntimeError, match="DASH_PASSWORD"):
        make_client()


def test_password_change_invalidates_existing_sessions(make_client, tmp_path):
    """Changing the password is the intuitive response to a stolen phone;
    it has to actually revoke access."""
    client = make_client(DASH_PASSWORD="old-pw", SESSION_SECRET="fixed")
    assert client.post("/login", data={"password": "old-pw"},
                       follow_redirects=False).status_code == 303
    cookie = client.cookies.get("tracker_session")
    assert client.get("/api/devices").status_code == 200

    # Same signing secret, new password: the old cookie must stop working.
    rotated = make_client(DASH_PASSWORD="new-pw", SESSION_SECRET="fixed")
    rotated.cookies.set("tracker_session", cookie)
    assert rotated.get("/api/devices").status_code == 401


def test_listener_name_is_sanitized(make_client):
    """Zone names are rendered into the dashboard; markup must never survive."""
    client = make_client(**PW)
    body = {"listener": '<img src=x onerror="alert(1)">',
            "tags": [{"mac": "D5:5A:2C:64:39:7A", "rssi": -60}]}
    assert client.post("/api/sighting", json=body,
                       headers={"X-Token": "test-token"}).status_code == 200
    client.post("/login", data={"password": "hunter2"})
    stored = client.get("/api/devices").json()[0]["listener"]
    for ch in "<>\"'=":
        assert ch not in stored


def test_pwa_assets_are_public(make_client):
    """The phone fetches these before it has a session."""
    client = make_client(**PW)
    m = client.get("/manifest.webmanifest")
    assert m.status_code == 200
    assert m.json()["display"] == "standalone"
    assert client.get("/static/icons/icon-192.png").status_code == 200


def test_service_worker_served_at_root(make_client):
    """Scope: a worker served from /static could only control /static."""
    client = make_client(**PW)
    r = client.get("/sw.js")
    assert r.status_code == 200
    assert "javascript" in r.headers["content-type"]
