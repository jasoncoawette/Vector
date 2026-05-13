"""Voice inbox — outbound messages from Vector to the user.

When the scheduler fires a daily brief (or any other recurring delivery)
the rendered text lands here. The desktop client polls /voice/inbox on
focus / open-app / every minute and drains pending rows.

Rows are persisted, not transient: if the desktop is offline at 8 AM,
the brief still gets delivered when the client comes back. The client
acks delivery with mark_delivered() so the same brief never plays twice.
"""
from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class InboxMessage:
    id: int
    kind: str            # "daily_brief", "weekly_brief", "alert", etc.
    text: str
    meta: dict[str, Any]
    created_at: float
    delivered_at: float | None


def _row_to_msg(row: sqlite3.Row) -> InboxMessage:
    return InboxMessage(
        id=int(row["id"]),
        kind=row["kind"],
        text=row["text"],
        meta=json.loads(row["meta_json"]) if row["meta_json"] else {},
        created_at=float(row["created_at"]),
        delivered_at=(
            float(row["delivered_at"]) if row["delivered_at"] is not None else None
        ),
    )


def enqueue(
    conn: sqlite3.Connection,
    *,
    kind: str,
    text: str,
    meta: dict[str, Any] | None = None,
) -> int:
    """Append a message to the inbox. Returns the new row id."""
    cur = conn.execute(
        "INSERT INTO voice_inbox(kind, text, meta_json, created_at) "
        "VALUES (?, ?, ?, ?)",
        (kind, text, json.dumps(meta or {}, sort_keys=True), time.time()),
    )
    return int(cur.lastrowid)


def pending(conn: sqlite3.Connection, *, limit: int = 20) -> list[InboxMessage]:
    """List undelivered messages, oldest first."""
    rows = conn.execute(
        "SELECT id, kind, text, meta_json, created_at, delivered_at "
        "FROM voice_inbox "
        "WHERE delivered_at IS NULL "
        "ORDER BY created_at ASC "
        "LIMIT ?",
        (limit,),
    ).fetchall()
    return [_row_to_msg(r) for r in rows]


def history(conn: sqlite3.Connection, *, limit: int = 100) -> list[InboxMessage]:
    """List recent inbox rows (delivered or not), newest first."""
    rows = conn.execute(
        "SELECT id, kind, text, meta_json, created_at, delivered_at "
        "FROM voice_inbox ORDER BY created_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [_row_to_msg(r) for r in rows]


def mark_delivered(conn: sqlite3.Connection, message_id: int) -> bool:
    """Mark one row as delivered. Returns True if a row was updated."""
    cur = conn.execute(
        "UPDATE voice_inbox SET delivered_at = ? "
        "WHERE id = ? AND delivered_at IS NULL",
        (time.time(), message_id),
    )
    return cur.rowcount > 0


def already_delivered_today(
    conn: sqlite3.Connection, *, kind: str, day_iso: str
) -> bool:
    """Has a row of this kind been enqueued today already?

    Used by the scheduler to avoid double-firing the daily brief if the
    process restarts mid-day. We check by `kind` + the local-date stored
    in meta so timezone shifts don't trip us up.
    """
    rows = conn.execute(
        "SELECT meta_json FROM voice_inbox WHERE kind = ? ORDER BY id DESC LIMIT 50",
        (kind,),
    ).fetchall()
    for r in rows:
        try:
            meta = json.loads(r["meta_json"]) if r["meta_json"] else {}
        except (TypeError, ValueError):
            continue
        if meta.get("day_iso") == day_iso:
            return True
    return False


def log_scheduler_tick(
    conn: sqlite3.Connection, *, key: str, outcome: str, detail: str | None = None
) -> None:
    """Record one scheduler decision for ops debugging.

    `outcome` is a short token: 'fired', 'skipped:not_due',
    'skipped:already_delivered', 'skipped:disabled', 'error:<reason>'.
    """
    conn.execute(
        "INSERT INTO scheduler_log(ts, key, outcome, detail) VALUES (?, ?, ?, ?)",
        (time.time(), key, outcome, detail),
    )


def scheduler_tail(
    conn: sqlite3.Connection, *, limit: int = 100
) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT ts, key, outcome, detail FROM scheduler_log "
        "ORDER BY ts DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]
