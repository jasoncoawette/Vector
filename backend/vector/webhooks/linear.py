from __future__ import annotations

import hashlib
import hmac
import sqlite3
import time
from dataclasses import dataclass
from typing import Any

from ..store import tasks as tasks_repo

MAX_PAYLOAD_BYTES = 256 * 1024
MAX_CLOCK_SKEW_S = 5 * 60


@dataclass
class LinearWebhookPayload:
    action: str
    type: str
    data: dict[str, Any]
    created_at: str | None = None


def verify_linear_signature(
    body: bytes, *, signature: str | None, secret: str, now: float | None = None
) -> None:
    """Constant-time HMAC-SHA256 check on the raw request body.

    Linear sends the signature in the `Linear-Signature` header.
    Raises ValueError on any failure so the caller can map to 401.
    """
    if not secret:
        raise ValueError("webhook secret not configured")
    if len(body) > MAX_PAYLOAD_BYTES:
        raise ValueError("payload too large")
    if not signature:
        raise ValueError("missing signature")
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature.strip()):
        raise ValueError("bad signature")


def _priority(value: Any) -> int:
    try:
        p = int(value)
    except (TypeError, ValueError):
        return 3
    return max(0, min(4, p))


def _normalize(payload: dict) -> LinearWebhookPayload | None:
    action = payload.get("action")
    ptype = payload.get("type")
    data = payload.get("data")
    if not isinstance(action, str) or not isinstance(ptype, str):
        return None
    if not isinstance(data, dict):
        return None
    return LinearWebhookPayload(
        action=action, type=ptype, data=data, created_at=payload.get("createdAt")
    )


def handle_linear_event(conn: sqlite3.Connection, payload: dict) -> dict:
    """Dispatch a Linear webhook to the local task store.

    Only `Issue` events update tasks. Other types (Comment, Project, etc.)
    are acknowledged but ignored — they don't affect Vector's daily picks.
    """
    parsed = _normalize(payload)
    if parsed is None:
        return {"ignored": True, "reason": "bad payload shape"}
    if parsed.type != "Issue":
        return {"ignored": True, "reason": f"type={parsed.type}"}

    data = parsed.data
    external_id = data.get("id")
    if not isinstance(external_id, str) or not external_id:
        return {"ignored": True, "reason": "missing id"}
    title = data.get("title") or "Untitled"
    state_name = (data.get("state") or {}).get("name", "")

    if parsed.action == "remove" or state_name in ("Canceled",):
        return {"ignored": True, "reason": "remove or canceled"}

    tid = tasks_repo.upsert(
        conn,
        external_id=external_id,
        title=str(title)[:500],
        source="linear",
        tag="outcome" if data.get("estimate", 0) >= 3 else "process",
        priority=_priority(data.get("priority", 3)),
        mission="stratus",
    )
    if state_name in ("Done", "Completed"):
        tasks_repo.mark_shipped(conn, tid)

    return {"ok": True, "task_id": tid, "action": parsed.action}
