"""Durable user preferences.

Keyed by a short string ('daily_brief', 'voice.style', ...) with a JSON
blob value. The keying convention is intentional: each key owns its own
schema; callers must round-trip through the helpers in this module.

The preferences table is intentionally tiny — anything larger than a
single user's settings belongs in `memories` or its own dedicated table.
"""
from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Preference:
    key: str
    value: Any
    updated_at: float


def get(conn: sqlite3.Connection, key: str) -> Preference | None:
    row = conn.execute(
        "SELECT key, value_json, updated_at FROM preferences WHERE key = ?",
        (key,),
    ).fetchone()
    if row is None:
        return None
    return Preference(
        key=row["key"],
        value=json.loads(row["value_json"]),
        updated_at=float(row["updated_at"]),
    )


def set_(conn: sqlite3.Connection, key: str, value: Any) -> Preference:
    """Set or overwrite a preference. Round-trips through JSON so we
    fail fast on un-serializable values."""
    blob = json.dumps(value, sort_keys=True)
    now = time.time()
    conn.execute(
        "INSERT INTO preferences(key, value_json, updated_at) "
        "VALUES (?, ?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value_json = excluded.value_json, "
        "  updated_at = excluded.updated_at",
        (key, blob, now),
    )
    return Preference(key=key, value=json.loads(blob), updated_at=now)


def clear(conn: sqlite3.Connection, key: str) -> bool:
    cur = conn.execute("DELETE FROM preferences WHERE key = ?", (key,))
    return cur.rowcount > 0


def list_all(conn: sqlite3.Connection) -> list[Preference]:
    rows = conn.execute(
        "SELECT key, value_json, updated_at FROM preferences ORDER BY key"
    ).fetchall()
    return [
        Preference(
            key=r["key"],
            value=json.loads(r["value_json"]),
            updated_at=float(r["updated_at"]),
        )
        for r in rows
    ]
