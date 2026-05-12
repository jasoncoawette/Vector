from __future__ import annotations

import asyncio
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest

from vector.google_oauth.flow import (
    OAuthError,
    OAuthFlow,
    build_consent_url,
    refresh_access_token,
)


def test_consent_url_includes_pkce_and_state():
    url, pending = build_consent_url(
        client_id="cid", scopes=["calendar"], port=7777
    )
    parsed = urlparse(url)
    qs = {k: v[0] for k, v in parse_qs(parsed.query).items()}
    assert qs["client_id"] == "cid"
    assert qs["scope"] == "calendar"
    assert qs["code_challenge_method"] == "S256"
    assert qs["state"] == pending.state
    assert qs["access_type"] == "offline"
    assert qs["prompt"] == "consent"
    assert "code_challenge" in qs
    # Verifier is held server-side, never on the wire.
    assert pending.code_verifier not in url


def test_consent_url_requires_inputs():
    with pytest.raises(OAuthError):
        build_consent_url(client_id="", scopes=["x"])
    with pytest.raises(OAuthError):
        build_consent_url(client_id="cid", scopes=[])


def test_each_consent_url_has_unique_state_and_verifier():
    a_url, a = build_consent_url(client_id="cid", scopes=["x"])
    b_url, b = build_consent_url(client_id="cid", scopes=["x"])
    assert a.state != b.state
    assert a.code_verifier != b.code_verifier


# ---- OAuthFlow.complete() ----


class _FakeResp:
    def __init__(self, payload: dict[str, Any], status: int = 200) -> None:
        self._payload = payload
        self.status_code = status
        self.text = str(payload)

    def json(self) -> dict[str, Any]:
        return self._payload


class _FakeHttp:
    """Records and answers token-endpoint POSTs."""

    def __init__(self, response: _FakeResp) -> None:
        self._response = response
        self.calls: list[tuple[str, dict, dict]] = []

    async def post(self, url, data=None, headers=None):
        self.calls.append((url, dict(data or {}), dict(headers or {})))
        return self._response

    async def aclose(self):
        pass


async def test_flow_exchanges_code_into_tokens():
    flow = OAuthFlow(client_id="cid", client_secret="cs", port=7777)
    consent_url = flow.start(["calendar"])
    state = list(flow._pending.keys())[0]

    http = _FakeHttp(
        _FakeResp(
            {
                "access_token": "AT",
                "refresh_token": "RT",
                "expires_in": 3599,
                "scope": "calendar",
                "token_type": "Bearer",
            }
        )
    )
    token, pending = await flow.complete(code="real-code", state=state, http=http)
    assert token.access_token == "AT"
    assert token.refresh_token == "RT"
    assert token.expires_in == 3599
    # And the body we POSTed echoes the PKCE verifier we created earlier.
    body = http.calls[0][1]
    assert body["code"] == "real-code"
    assert body["code_verifier"] == pending.code_verifier
    assert body["grant_type"] == "authorization_code"
    assert body["redirect_uri"].endswith(":7777/oauth/google/callback")


async def test_unknown_state_rejected():
    flow = OAuthFlow(client_id="cid", client_secret="cs")
    with pytest.raises(OAuthError, match="state"):
        await flow.complete(code="x", state="never-issued", http=_FakeHttp(_FakeResp({})))


async def test_state_consumed_after_use():
    flow = OAuthFlow(client_id="cid", client_secret="cs")
    flow.start(["calendar"])
    state = list(flow._pending.keys())[0]
    http = _FakeHttp(
        _FakeResp(
            {
                "access_token": "AT",
                "refresh_token": "RT",
                "expires_in": 1,
                "scope": "c",
                "token_type": "Bearer",
            }
        )
    )
    await flow.complete(code="c", state=state, http=http)
    # Second attempt with the same state must fail.
    with pytest.raises(OAuthError):
        await flow.complete(code="c", state=state, http=http)


async def test_token_endpoint_4xx_becomes_oauth_error():
    flow = OAuthFlow(client_id="cid", client_secret="cs")
    flow.start(["calendar"])
    state = list(flow._pending.keys())[0]
    http = _FakeHttp(_FakeResp({"error": "invalid_grant"}, status=400))
    with pytest.raises(OAuthError, match="400"):
        await flow.complete(code="x", state=state, http=http)


async def test_response_without_access_token_rejected():
    flow = OAuthFlow(client_id="cid", client_secret="cs")
    flow.start(["calendar"])
    state = list(flow._pending.keys())[0]
    http = _FakeHttp(_FakeResp({"error": "no_access_token"}, status=200))
    with pytest.raises(OAuthError, match="missing access_token"):
        await flow.complete(code="x", state=state, http=http)


async def test_refresh_uses_refresh_grant_type():
    http = _FakeHttp(
        _FakeResp(
            {
                "access_token": "NEW",
                "expires_in": 3600,
                "scope": "calendar",
                "token_type": "Bearer",
            }
        )
    )
    out = await refresh_access_token(
        refresh_token="RT", client_id="cid", client_secret="cs", http=http
    )
    assert out.access_token == "NEW"
    assert http.calls[0][1]["grant_type"] == "refresh_token"
    assert http.calls[0][1]["refresh_token"] == "RT"


async def test_refresh_requires_refresh_token():
    with pytest.raises(OAuthError):
        await refresh_access_token(refresh_token="", client_id="c", client_secret="s")


def test_consent_sweep_drops_stale_entries(monkeypatch):
    flow = OAuthFlow(client_id="cid", client_secret="cs")
    flow.start(["c"])
    state = list(flow._pending.keys())[0]
    # Roll the entry back beyond the TTL by mutating issued_at directly.
    flow._pending[state].issued_at -= 60 * 60
    flow._sweep()
    assert state not in flow._pending
