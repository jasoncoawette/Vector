from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from vector.app import app
from vector.config import get_settings
from vector.deps import set_db, set_oauth_flow, set_token_store
from vector.google_oauth import OAuthFlow, TokenStore, generate_token_key
from vector.store import connect


@pytest.fixture()
def client(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("VECTOR_OAUTH_TOKEN_KEY", generate_token_key())
    conn = connect(tmp_path / "v.db", check_integrity=False)
    set_db(conn)
    set_oauth_flow(OAuthFlow(client_id="cid", client_secret="cs", port=7777))
    set_token_store(TokenStore(conn))
    yield TestClient(app)
    set_token_store(None)
    set_oauth_flow(None)
    set_db(None)
    conn.close()


def test_start_returns_consent_url(client):
    r = client.post(
        "/oauth/google/start",
        json={"scopes": ["https://www.googleapis.com/auth/calendar.events"]},
    )
    assert r.status_code == 200
    url = r.json()["url"]
    assert url.startswith("https://accounts.google.com/")
    assert "code_challenge=" in url
    assert "state=" in url


def test_start_rejects_empty_scopes(client):
    r = client.post("/oauth/google/start", json={"scopes": []})
    assert r.status_code == 422  # pydantic min_length


def test_callback_missing_code_or_state_400(client):
    r = client.get("/oauth/google/callback")
    assert r.status_code == 400
    r = client.get("/oauth/google/callback?state=x")
    assert r.status_code == 400


def test_callback_error_param_surfaced(client):
    r = client.get("/oauth/google/callback?error=access_denied")
    assert r.status_code == 400
    assert "access_denied" in r.json()["detail"]


def test_callback_unknown_state_400(client):
    r = client.get("/oauth/google/callback?code=c&state=never-issued")
    assert r.status_code == 400


def test_status_lists_accounts(client):
    # Empty initially.
    body = client.get("/oauth/google/status").json()
    assert body["configured"] is True
    assert body["accounts"] == []


def test_revoke_requires_bearer_when_set(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("VECTOR_OAUTH_TOKEN_KEY", generate_token_key())
    conn = connect(tmp_path / "v.db", check_integrity=False)
    set_db(conn)
    set_oauth_flow(OAuthFlow(client_id="cid", client_secret="cs"))
    store = TokenStore(conn)
    store.save(account="default", scopes=["s"], refresh_token="R")
    set_token_store(store)
    s = get_settings()
    original = s.backend_bearer
    s.backend_bearer = "test-bearer"
    try:
        c = TestClient(app)
        unauth = c.delete("/oauth/google/default")
        assert unauth.status_code == 401
        ok = c.delete(
            "/oauth/google/default",
            headers={"Authorization": "Bearer test-bearer"},
        )
        assert ok.status_code == 200
    finally:
        s.backend_bearer = original
        set_token_store(None)
        set_oauth_flow(None)
        set_db(None)
        conn.close()


def test_revoke_unknown_account_404(client):
    r = client.delete("/oauth/google/missing")
    assert r.status_code == 404


def test_oauth_unconfigured_returns_503(tmp_path: Path):
    conn = connect(tmp_path / "v.db", check_integrity=False)
    set_db(conn)
    set_oauth_flow(None)
    set_token_store(None)
    try:
        c = TestClient(app)
        r = c.post(
            "/oauth/google/start",
            json={"scopes": ["calendar"]},
        )
        assert r.status_code == 503
    finally:
        set_db(None)
        conn.close()
