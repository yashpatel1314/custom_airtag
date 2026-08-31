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
