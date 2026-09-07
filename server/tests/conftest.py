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
        for key in ("DASH_PASSWORD", "SESSION_SECRET",
                    "ALLOW_OPEN_DASHBOARD"):
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
