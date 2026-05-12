"""Append-only event log keyed by trace_id.

Every meaningful step in a turn / run / tool call / verifier check emits
one row. The trace_id lets you reconstruct a full chain by:

    SELECT * FROM events WHERE trace_id = ? ORDER BY ts ASC
"""
from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from typing import Any

from ..tracing import current_trace_id

MAX_META_BYTES = 8 * 1024


@dataclass
class Event:
    id: int
    ts: float
    trace_id: str | None
    run_id: str | None
    kind: str
    cost_delta: float | None
    latency_ms: float | None
    meta: dict


def emit(
    conn: sqlite3.Connection,
    kind: str,
    *,
    run_id: str | None = None,
    cost_delta: float | None = None,
    latency_ms: float | None = None,
    meta: dict | None = None,
    trace_id: str | None = None,
) -> int:
    payload = json.dumps(meta or {}, default=str)
    if len(payload) > MAX_META_BYTES:
        # Truncate at the boundary; preserve the kind + a marker.
        payload = payload[:MAX_META_BYTES] + '..."truncated":true}'
    tid = trace_id if trace_id is not None else current_trace_id()
    cur = conn.execute(
        """
        INSERT INTO events(ts, trace_id, run_id, kind, cost_delta, latency_ms, meta)
        VALUES(?, ?, ?, ?, ?, ?, ?)
        """,
        (time.time(), tid, run_id, kind, cost_delta, latency_ms, payload),
    )
    return int(cur.lastrowid)


def by_trace(conn: sqlite3.Connection, trace_id: str) -> list[Event]:
    rows = conn.execute(
        """
        SELECT id, ts, trace_id, run_id, kind, cost_delta, latency_ms, meta
        FROM events WHERE trace_id = ? ORDER BY ts ASC
        """,
        (trace_id,),
    ).fetchall()
    return [_row(r) for r in rows]


def by_run(conn: sqlite3.Connection, run_id: str) -> list[Event]:
    rows = conn.execute(
        """
        SELECT id, ts, trace_id, run_id, kind, cost_delta, latency_ms, meta
        FROM events WHERE run_id = ? ORDER BY ts ASC
        """,
        (run_id,),
    ).fetchall()
    return [_row(r) for r in rows]


def recent(conn: sqlite3.Connection, *, limit: int = 200) -> list[Event]:
    limit = max(1, min(limit, 2000))
    rows = conn.execute(
        """
        SELECT id, ts, trace_id, run_id, kind, cost_delta, latency_ms, meta
        FROM events ORDER BY ts DESC LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [_row(r) for r in rows]


def _row(r: sqlite3.Row) -> Event:
    try:
        meta = json.loads(r["meta"]) if r["meta"] else {}
    except json.JSONDecodeError:
        meta = {"_unparseable": r["meta"]}
    return Event(
        id=r["id"],
        ts=r["ts"],
        trace_id=r["trace_id"],
        run_id=r["run_id"],
        kind=r["kind"],
        cost_delta=r["cost_delta"],
        latency_ms=r["latency_ms"],
        meta=meta if isinstance(meta, dict) else {},
    )
