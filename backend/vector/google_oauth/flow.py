"""Google OAuth 2.0 authorization-code flow with PKCE.

We use the "loopback IP" variant: the redirect URI is
http://127.0.0.1:7777/oauth/google/callback, which Google accepts for
desktop apps without any TLS dance. PKCE protects against the
authorization-code interception attack on the loopback hop.

State machine:
  1. build_consent_url(scopes) -> URL + state + verifier; we stash
     (state, verifier, scopes) in memory keyed by state.
  2. user hits the URL in a browser, grants access, Google redirects
     to our callback with ?code=... &state=...
  3. exchange_code(code, state) -> POST to Google's token endpoint
     with the verifier; on success returns access_token + refresh_token
     + expiry. We persist via TokenStore.
  4. refresh_access_token(refresh_token) when the access token expires.

We never store the client_secret in the DB or logs. It lives in env.
"""
from __future__ import annotations

import base64
import hashlib
import logging
import secrets
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlencode

import httpx

logger = logging.getLogger("vector.google_oauth.flow")

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
LOOPBACK_REDIRECT = "http://127.0.0.1:{port}/oauth/google/callback"

# Pending consent state TTL — Google sessions expire fast; ours can be
# tighter. 10 minutes is generous; usually users click "allow" in
# seconds.
CONSENT_TTL_S = 10 * 60


class OAuthError(RuntimeError):
    pass


@dataclass
class PendingConsent:
    state: str
    code_verifier: str
    scopes: tuple[str, ...]
    issued_at: float


def _pkce_pair() -> tuple[str, str]:
    """Return (verifier, challenge). Challenge is S256 of the verifier."""
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(48)).rstrip(b"=").decode()
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    return verifier, challenge


def build_consent_url(
    *,
    client_id: str,
    scopes: list[str],
    port: int = 7777,
    extra: dict[str, str] | None = None,
) -> tuple[str, PendingConsent]:
    """Build the Google consent URL plus the pending-consent record the
    caller must keep until the callback fires."""
    if not client_id:
        raise OAuthError("client_id required")
    if not scopes:
        raise OAuthError("at least one scope required")
    verifier, challenge = _pkce_pair()
    state = secrets.token_urlsafe(24)
    params = {
        "client_id": client_id,
        "redirect_uri": LOOPBACK_REDIRECT.format(port=port),
        "response_type": "code",
        "scope": " ".join(scopes),
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": state,
        "access_type": "offline",
        "prompt": "consent",  # ensure refresh_token is returned each time
        "include_granted_scopes": "true",
    }
    if extra:
        params.update(extra)
    url = f"{AUTH_URL}?{urlencode(params)}"
    pending = PendingConsent(
        state=state,
        code_verifier=verifier,
        scopes=tuple(scopes),
        issued_at=time.time(),
    )
    return url, pending


@dataclass
class TokenResponse:
    access_token: str
    refresh_token: str | None
    expires_in: int
    scope: str
    token_type: str

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> "TokenResponse":
        if "access_token" not in data:
            raise OAuthError(f"missing access_token in response: {data.get('error', data)}")
        return cls(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token"),
            expires_in=int(data.get("expires_in", 0)),
            scope=data.get("scope", ""),
            token_type=data.get("token_type", "Bearer"),
        )


async def exchange_code(
    *,
    code: str,
    client_id: str,
    client_secret: str,
    code_verifier: str,
    port: int = 7777,
    http: httpx.AsyncClient | None = None,
) -> TokenResponse:
    """Trade an authorization code for an access + refresh token."""
    if not code:
        raise OAuthError("missing code")
    if not client_id or not client_secret:
        raise OAuthError("client_id and client_secret required")
    body = {
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "code_verifier": code_verifier,
        "redirect_uri": LOOPBACK_REDIRECT.format(port=port),
        "grant_type": "authorization_code",
    }
    return await _post_token(body, http)


async def refresh_access_token(
    *,
    refresh_token: str,
    client_id: str,
    client_secret: str,
    http: httpx.AsyncClient | None = None,
) -> TokenResponse:
    if not refresh_token:
        raise OAuthError("refresh_token required")
    body = {
        "refresh_token": refresh_token,
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "refresh_token",
    }
    return await _post_token(body, http)


async def _post_token(
    body: dict[str, str], http: httpx.AsyncClient | None
) -> TokenResponse:
    owned = http is None
    client = http or httpx.AsyncClient(timeout=10.0)
    try:
        r = await client.post(
            TOKEN_URL,
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if r.status_code >= 400:
            raise OAuthError(f"google token endpoint http {r.status_code}: {r.text[:300]}")
        return TokenResponse.from_payload(r.json())
    finally:
        if owned:
            await client.aclose()


@dataclass
class OAuthFlow:
    """In-memory pending-consent registry. One per backend process.

    Wires together build_consent_url() + exchange_code() with state
    bookkeeping so the route handler doesn't have to manage TTLs."""

    client_id: str
    client_secret: str
    port: int = 7777
    _pending: dict[str, PendingConsent] = field(default_factory=dict)

    def start(self, scopes: list[str]) -> str:
        """Return the consent URL the user should open."""
        self._sweep()
        url, pending = build_consent_url(
            client_id=self.client_id, scopes=scopes, port=self.port
        )
        self._pending[pending.state] = pending
        return url

    async def complete(
        self, *, code: str, state: str, http: httpx.AsyncClient | None = None
    ) -> tuple[TokenResponse, PendingConsent]:
        self._sweep()
        pending = self._pending.pop(state, None)
        if pending is None:
            raise OAuthError("unknown or expired state")
        token = await exchange_code(
            code=code,
            client_id=self.client_id,
            client_secret=self.client_secret,
            code_verifier=pending.code_verifier,
            port=self.port,
            http=http,
        )
        return token, pending

    def _sweep(self) -> None:
        now = time.time()
        for state, p in list(self._pending.items()):
            if now - p.issued_at > CONSENT_TTL_S:
                self._pending.pop(state, None)
