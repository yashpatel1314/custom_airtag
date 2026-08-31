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


def test_login_page_renders_form():
    html = auth.login_page_html()
    assert '<form method="post" action="/login"' in html
    assert 'type="password"' in html
    assert 'name="password"' in html


def test_login_page_shows_error_when_given():
    assert "Incorrect password." in auth.login_page_html("Incorrect password.")
    assert "Incorrect password." not in auth.login_page_html()
