"""Persistent agent-run history.

The in-memory `AgentManager._runs` dict gets a write-through to this
table on every status change. Survives backend restart so the
debugging agent (and the /runs view) can read history beyond memory.

We crash-recover by marking any RUNNING / QUEUED rows as
INTERRUPTED at startup — they were in flight when the process died
and won't resume.
"""
from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass


@dataclass
class StoredRun:
    id: str
    trace_id: str | None
    type: str
    prompt: str
    files: list[str]
    status: str
    output: str
    error: str
    cost_usd: float
    fallback_used: bool
    attempts_used: int
    max_attempts: int
    last_verifier_reason: str | None
    queued_at: float
    started_at: float | None
    ended_at: float | None
    updated_at: float


def upsert_from_summary(conn: sqlite3.Connection, summary: dict, queued_at: float | None = None) -> None:
    """Insert or update one run row from a Run.summary() dict."""
    now = time.time()
    conn.execute(
        """
        INSERT INTO runs(
            id, trace_id, type, prompt, files, status, output, error,
            cost_usd, fallback_used, attempts_used, max_attempts,
            last_verifier_reason, queued_at, started_at, ended_at, updated_at
        ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            trace_id = excluded.trace_id,
            status = excluded.status,
            output = excluded.output,
            error = excluded.error,
            cost_usd = excluded.cost_usd,
            fallback_used = excluded.fallback_used,
            attempts_used = excluded.attempts_used,
            max_attempts = excluded.max_attempts,
            last_verifier_reason = excluded.last_verifier_reason,
            started_at = COALESCE(excluded.started_at, runs.started_at),
            ended_at = excluded.ended_at,
            updated_at = excluded.updated_at
        """,
        (
            summary["id"],
            summary.get("trace_id"),
            summary["type"],
            summary.get("prompt", ""),
            json.dumps(summary.get("files") or []),
            summary["status"],
            summary.get("output", ""),
            summary.get("error", ""),
            float(summary.get("cost_usd") or 0.0),
            1 if summary.get("fallback_used") else 0,
            int(summary.get("attempts_used") or 0),
            int(summary.get("max_attempts") or 1),
            summary.get("last_verifier_reason"),
            queued_at if queued_at is not None else now,
            None,  # started_at written by COALESCE only if first set
            None if summary["status"] in ("queued", "running") else now,
            now,
        ),
    )


def mark_interrupted_on_startup(conn: sqlite3.Connection) -> int:
    """Mark any run rows left in queued/running state as 'interrupted'.

    Called once at app startup to clean up state from a previous crash.
    Returns the count of rows updated."""
    now = time.time()
    cur = conn.execute(
        """
        UPDATE runs
        SET status = 'interrupted',
            error = COALESCE(NULLIF(error, ''), 'backend restarted while running'),
            ended_at = COALESCE(ended_at, ?),
            updated_at = ?
        WHERE status IN ('queued', 'running')
        """,
        (now, now),
    )
    return cur.rowcount


def get(conn: sqlite3.Connection, run_id: str) -> StoredRun | None:
    r = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    if r is None:
        return None
    return _row(r)


def recent(
    conn: sqlite3.Connection, *, limit: int = 100, status: str | None = None
) -> list[StoredRun]:
    limit = max(1, min(limit, 500))
    if status:
        rows = conn.execute(
            "SELECT * FROM runs WHERE status = ? ORDER BY updated_at DESC LIMIT ?",
            (status, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM runs ORDER BY updated_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [_row(r) for r in rows]


def by_trace(conn: sqlite3.Connection, trace_id: str) -> list[StoredRun]:
    rows = conn.execute(
        "SELECT * FROM runs WHERE trace_id = ? ORDER BY queued_at ASC",
        (trace_id,),
    ).fetchall()
    return [_row(r) for r in rows]


def _row(r: sqlite3.Row) -> StoredRun:
    try:
        files = json.loads(r["files"]) if r["files"] else []
    except json.JSONDecodeError:
        files = []
    return StoredRun(
        id=r["id"],
        trace_id=r["trace_id"],
        type=r["type"],
        prompt=r["prompt"],
        files=files if isinstance(files, list) else [],
        status=r["status"],
        output=r["output"] or "",
        error=r["error"] or "",
        cost_usd=r["cost_usd"],
        fallback_used=bool(r["fallback_used"]),
        attempts_used=r["attempts_used"],
        max_attempts=r["max_attempts"],
        last_verifier_reason=r["last_verifier_reason"],
        queued_at=r["queued_at"],
        started_at=r["started_at"],
        ended_at=r["ended_at"],
        updated_at=r["updated_at"],
    )
