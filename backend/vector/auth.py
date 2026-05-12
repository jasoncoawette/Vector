from __future__ import annotations

import hmac

from fastapi import Header, HTTPException, WebSocket, status

from .config import get_settings


def require_bearer(authorization: str | None = Header(default=None)) -> None:
    """Constant-time bearer check.

    When `backend_bearer` is empty in config (e.g. local dev or tests),
    no auth is required. When set, the Authorization header must be
    `Bearer <token>` and match the configured value.
    """
    expected = get_settings().backend_bearer
    if not expected:
        return
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    presented = authorization[len("Bearer ") :].strip()
    if not hmac.compare_digest(presented, expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "bad bearer token")


async def check_ws_bearer(ws: WebSocket) -> bool:
    """WebSocket bearer check.

    Browsers can't set the `Authorization` header on a WS handshake, so
    the token comes via `?token=...` query param. Returns True if the
    request is authorized (or auth is disabled). On failure, closes the
    socket with policy-violation (1008) and returns False — the caller
    must not call `accept()` after a False return.
    """
    expected = get_settings().backend_bearer
    if not expected:
        return True
    presented = ws.query_params.get("token", "")
    if presented and hmac.compare_digest(presented, expected):
        return True
    await ws.close(code=1008)
    return False
