"""Authenticated Google API client shared by Calendar and Gmail.

Pulls the refresh token out of the TokenStore on every request, mints
a fresh access token if the cached one's about to expire, and POSTs /
GETs to the requested endpoint. Access tokens get cached on the
TokenStore so the next 50-minute window of calls doesn't re-spend
the refresh hop.

We never read the unencrypted refresh token into local state — it
lives in memory only for the milliseconds the refresh call takes.
"""
from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from ..google_oauth import OAuthError, TokenStore, refresh_access_token

logger = logging.getLogger("vector.tools.google_api")

# Refresh access tokens this many seconds before their real expiry so
# we don't race a token that's about to lapse mid-request.
REFRESH_SKEW_S = 60

DEFAULT_TIMEOUT_S = 15.0


class GoogleAuthError(RuntimeError):
    pass


class GoogleApiClient:
    """Authenticated wrapper around httpx with refresh-on-401 + cache.

    `client_id` + `client_secret` come from settings, NOT from the
    token store. The store only holds per-account refresh tokens."""

    def __init__(
        self,
        store: TokenStore,
        *,
        client_id: str,
        client_secret: str,
        http: httpx.AsyncClient | None = None,
        account: str = "default",
    ) -> None:
        if not client_id or not client_secret:
            raise GoogleAuthError("oauth client_id + client_secret required")
        self._store = store
        self._client_id = client_id
        self._client_secret = client_secret
        self._http = http
        self._owned_http = False
        self.account = account

    async def _client(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=DEFAULT_TIMEOUT_S)
            self._owned_http = True
        return self._http

    async def aclose(self) -> None:
        if self._owned_http and self._http is not None:
            await self._http.aclose()

    async def _access_token(self, *, force_refresh: bool = False) -> str:
        tok = self._store.get(self.account)
        if tok is None:
            raise GoogleAuthError(
                f"no Google account '{self.account}' authorized; "
                "complete the consent flow at POST /oauth/google/start"
            )
        # Use cached access token if fresh enough.
        if (
            not force_refresh
            and tok.access_token
            and tok.access_token_expires_at - time.time() > REFRESH_SKEW_S
        ):
            return tok.access_token
        # Otherwise refresh.
        refresh = self._store.get_refresh_token(self.account)
        if not refresh:
            raise GoogleAuthError("missing refresh token; re-authorize")
        try:
            resp = await refresh_access_token(
                refresh_token=refresh,
                client_id=self._client_id,
                client_secret=self._client_secret,
                http=self._http,
            )
        except OAuthError as e:
            raise GoogleAuthError(f"refresh failed: {e}") from e
        # Persist the new access token + expiry. Refresh tokens
        # rotate rarely, but if Google sends a new one save that too.
        self._store.update_access_token(
            account=self.account,
            access_token=resp.access_token,
            expires_in=resp.expires_in,
        )
        if resp.refresh_token and resp.refresh_token != refresh:
            self._store.save(
                account=self.account,
                scopes=tok.scopes.split(),
                refresh_token=resp.refresh_token,
                access_token=resp.access_token,
                expires_in=resp.expires_in,
            )
        return resp.access_token

    async def request(
        self,
        method: str,
        url: str,
        *,
        params: dict | None = None,
        json_body: dict | None = None,
        retry_on_401: bool = True,
    ) -> Any:
        """One authenticated request. On 401 we force-refresh once and
        replay (covers tokens revoked or skew-edge cases)."""
        client = await self._client()
        token = await self._access_token()
        headers = {"Authorization": f"Bearer {token}"}
        r = await client.request(method, url, params=params, json=json_body, headers=headers)
        if r.status_code == 401 and retry_on_401:
            token = await self._access_token(force_refresh=True)
            headers["Authorization"] = f"Bearer {token}"
            r = await client.request(method, url, params=params, json=json_body, headers=headers)
        if r.status_code >= 400:
            raise GoogleAuthError(f"google api http {r.status_code}: {r.text[:300]}")
        try:
            return r.json()
        except ValueError as e:
            raise GoogleAuthError(f"bad json from google: {e}") from e
