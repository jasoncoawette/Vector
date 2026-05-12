"""GoogleApiClient: refresh-on-stale + retry-on-401 behavior.

We don't hit the real Google endpoints; an in-memory FakeHttp records
calls and yields canned responses. The TokenStore is the real one
backed by a tmp SQLite DB so we exercise the encrypt/decrypt round-trip.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from vector.google_oauth import TokenStore, generate_token_key
from vector.store import connect
from vector.tools.google_api import GoogleApiClient, GoogleAuthError


@dataclass
class _Resp:
    status_code: int
    payload: Any
    text: str = ""

    def json(self) -> Any:
        return self.payload


class _FakeHttp:
    def __init__(self, responses: list[_Resp]) -> None:
        self._responses = list(responses)
        self.calls: list[dict] = []

    async def request(self, method, url, params=None, json=None, headers=None):
        self.calls.append(
            {
                "method": method,
                "url": url,
                "params": dict(params or {}),
                "json": dict(json) if json else None,
                "headers": dict(headers or {}),
            }
        )
        return self._responses.pop(0)

    async def post(self, url, data=None, headers=None):
        # Used by refresh_access_token.
        self.calls.append({"method": "POST", "url": url, "data": dict(data or {})})
        return self._responses.pop(0)

    async def aclose(self):
        pass


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("VECTOR_OAUTH_TOKEN_KEY", generate_token_key())


@pytest.fixture()
def store(tmp_path: Path):
    conn = connect(tmp_path / "v.db", check_integrity=False)
    s = TokenStore(conn)
    s.save(account="default", scopes=["calendar"], refresh_token="RT", access_token=None)
    yield s
    conn.close()


def test_constructor_requires_oauth_client(store):
    with pytest.raises(GoogleAuthError):
        GoogleApiClient(store=store, client_id="", client_secret="cs")


async def test_uses_cached_access_token_when_fresh(store):
    # Cache an access token that's still valid for 10 minutes.
    store.update_access_token(account="default", access_token="AT-cached", expires_in=600)
    http = _FakeHttp([_Resp(200, {"ok": True})])
    client = GoogleApiClient(
        store=store, client_id="cid", client_secret="cs", http=http
    )
    out = await client.request("GET", "https://example.com/x")
    assert out == {"ok": True}
    # Only ONE call (the actual API GET), no refresh hop.
    assert len(http.calls) == 1
    assert http.calls[0]["headers"]["Authorization"] == "Bearer AT-cached"


async def test_refreshes_when_access_token_stale(store):
    # Cache an access token that's almost expired (under REFRESH_SKEW_S).
    store.update_access_token(account="default", access_token="AT-old", expires_in=10)
    http = _FakeHttp(
        [
            _Resp(
                200,
                {
                    "access_token": "AT-new",
                    "expires_in": 3600,
                    "scope": "calendar",
                    "token_type": "Bearer",
                },
            ),
            _Resp(200, {"ok": True}),
        ]
    )
    client = GoogleApiClient(
        store=store, client_id="cid", client_secret="cs", http=http
    )
    out = await client.request("GET", "https://example.com/x")
    assert out == {"ok": True}
    # First call was a refresh POST; second was the actual GET.
    assert http.calls[0]["method"] == "POST"
    assert "refresh_token" in http.calls[0]["data"]
    assert http.calls[1]["headers"]["Authorization"] == "Bearer AT-new"


async def test_refreshes_and_retries_on_401(store):
    # Cache "fresh" token but server says it's bad.
    store.update_access_token(account="default", access_token="AT-old", expires_in=600)
    http = _FakeHttp(
        [
            _Resp(401, {"error": "expired"}, text="expired"),
            _Resp(
                200,
                {
                    "access_token": "AT-new",
                    "expires_in": 3600,
                    "scope": "calendar",
                    "token_type": "Bearer",
                },
            ),
            _Resp(200, {"ok": True}),
        ]
    )
    client = GoogleApiClient(
        store=store, client_id="cid", client_secret="cs", http=http
    )
    out = await client.request("GET", "https://example.com/x")
    assert out == {"ok": True}
    # Sequence: original GET (401), refresh POST, retry GET (200).
    methods = [c["method"] for c in http.calls]
    assert methods == ["GET", "POST", "GET"]
    assert http.calls[2]["headers"]["Authorization"] == "Bearer AT-new"


async def test_unknown_account_raises(tmp_path: Path):
    conn = connect(tmp_path / "v.db", check_integrity=False)
    try:
        empty_store = TokenStore(conn)  # no save() call
        http = _FakeHttp([])
        client = GoogleApiClient(
            store=empty_store, client_id="cid", client_secret="cs", http=http
        )
        with pytest.raises(GoogleAuthError, match="no Google account"):
            await client.request("GET", "https://example.com/x")
    finally:
        conn.close()


async def test_4xx_other_than_401_raises(store):
    store.update_access_token(account="default", access_token="AT", expires_in=600)
    http = _FakeHttp([_Resp(403, {"error": "forbidden"}, text="forbidden")])
    client = GoogleApiClient(
        store=store, client_id="cid", client_secret="cs", http=http
    )
    with pytest.raises(GoogleAuthError, match="403"):
        await client.request("GET", "https://example.com/x")


async def test_bad_json_response_raises(store):
    store.update_access_token(account="default", access_token="AT", expires_in=600)

    class _BadJsonResp:
        status_code = 200
        text = "not json"

        def json(self):
            raise ValueError("bad json")

    http = _FakeHttp([_BadJsonResp()])
    client = GoogleApiClient(
        store=store, client_id="cid", client_secret="cs", http=http
    )
    with pytest.raises(GoogleAuthError, match="bad json"):
        await client.request("GET", "https://example.com/x")
