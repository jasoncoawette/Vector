from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import time
from typing import Any

logger = logging.getLogger("vector.audit")

_sink: sqlite3.Connection | None = None


def set_sink(conn: sqlite3.Connection | None) -> None:
    global _sink
    _sink = conn


def _hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, default=str).encode()
    return hashlib.sha256(payload).hexdigest()[:16]


def record(tool: str, caller: str, args: dict, result: Any, ok: bool) -> dict:
    entry = {
        "ts": time.time(),
        "tool": tool,
        "caller": caller,
        "args_hash": _hash(args),
        "result_hash": _hash(result),
        "ok": ok,
    }
    logger.info("audit %s", json.dumps(entry))
    if _sink is not None:
        reason = None
        if isinstance(result, dict):
            reason = result.get("reason")
        try:
            _sink.execute(
                """
                INSERT INTO audit_log(ts, tool, caller, args_hash, result_hash, ok, reason)
                VALUES(?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry["ts"],
                    tool,
                    caller,
                    entry["args_hash"],
                    entry["result_hash"],
                    1 if ok else 0,
                    reason,
                ),
            )
        except sqlite3.Error as e:
            logger.warning("audit sink failed: %s", e)
    return entry


def tail(conn: sqlite3.Connection, *, limit: int = 100) -> list[dict]:
    limit = max(1, min(limit, 500))
    rows = conn.execute(
        "SELECT ts, tool, caller, args_hash, result_hash, ok, reason FROM audit_log ORDER BY ts DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [
        {
            "ts": r["ts"],
            "tool": r["tool"],
            "caller": r["caller"],
            "args_hash": r["args_hash"],
            "result_hash": r["result_hash"],
            "ok": bool(r["ok"]),
            "reason": r["reason"],
        }
        for r in rows
    ]
