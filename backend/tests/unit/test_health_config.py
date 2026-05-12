from __future__ import annotations

from fastapi.testclient import TestClient

from vector.app import app
from vector.config import Settings, get_settings


def test_healthz_returns_build_hash():
    client = TestClient(app)
    r = client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert "build" in body


def test_config_redacts_secrets(monkeypatch):
    s = Settings(
        anthropic_api_key="sk-real-key-do-not-leak",
        elevenlabs_api_key="el-real-key",
    )
    redacted = s.redacted()
    assert redacted["anthropic_api_key"] == "***redacted***"
    assert redacted["elevenlabs_api_key"] == "***redacted***"
    assert "sk-real-key-do-not-leak" not in str(redacted)


def test_config_post_requires_bearer():
    client = TestClient(app)
    r = client.post("/config", json={})
    assert r.status_code == 401


def test_config_get_returns_no_plaintext_secrets():
    client = TestClient(app)
    r = client.get("/config")
    assert r.status_code == 200
    body = r.json()
    for key in ("anthropic_api_key", "elevenlabs_api_key", "deepgram_api_key"):
        assert body[key] in ("", "***redacted***")


def test_get_settings_is_cached():
    a = get_settings()
    b = get_settings()
    assert a is b
