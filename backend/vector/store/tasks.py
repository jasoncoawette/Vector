from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass


@dataclass
class Task:
    id: int
    title: str
    source: str
    tag: str
    priority: int
    mission: str
    status: str
    external_id: str | None = None
    shipped_at: float | None = None


def upsert(
    conn: sqlite3.Connection,
    *,
    external_id: str | None,
    title: str,
    source: str,
    tag: str = "process",
    priority: int = 3,
    mission: str = "stratus",
) -> int:
    now = time.time()
    if external_id:
        row = conn.execute(
            "SELECT id FROM tasks WHERE external_id = ?", (external_id,)
        ).fetchone()
        if row:
            conn.execute(
                "UPDATE tasks SET title=?, source=?, tag=?, priority=?, mission=? WHERE id=?",
                (title, source, tag, priority, mission, row["id"]),
            )
            return row["id"]
    cur = conn.execute(
        """
        INSERT INTO tasks(external_id, title, source, tag, priority, mission, created_at)
        VALUES(?, ?, ?, ?, ?, ?, ?)
        """,
        (external_id, title, source, tag, priority, mission, now),
    )
    return int(cur.lastrowid)


def list_open(conn: sqlite3.Connection) -> list[Task]:
    rows = conn.execute(
        "SELECT * FROM tasks WHERE status = 'open' ORDER BY priority ASC, id ASC"
    ).fetchall()
    return [_row(r) for r in rows]


def mark_shipped(conn: sqlite3.Connection, task_id: int) -> None:
    conn.execute(
        "UPDATE tasks SET status='shipped', shipped_at=? WHERE id=?",
        (time.time(), task_id),
    )


def get(conn: sqlite3.Connection, task_id: int) -> Task | None:
    r = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    return _row(r) if r else None


def _row(r: sqlite3.Row) -> Task:
    return Task(
        id=r["id"],
        title=r["title"],
        source=r["source"],
        tag=r["tag"],
        priority=r["priority"],
        mission=r["mission"],
        status=r["status"],
        external_id=r["external_id"],
        shipped_at=r["shipped_at"],
    )
