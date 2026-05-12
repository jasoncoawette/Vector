from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass

from ..store import metrics as metrics_store

MISSION_METRIC_NAMES = (
    "us_compute_share",
    "china_compute_output",
    "stratus_share_us_mil",
)

MAX_CHOKE_POINTS_PER_WEEK = 3


@dataclass
class ChokePoint:
    rank: int
    title: str
    note: str | None
    recorded_at: float


def seed_mission_baseline(conn: sqlite3.Connection) -> dict[str, int]:
    """Idempotent: only writes a baseline value if no point exists for the metric."""
    written: dict[str, int] = {}
    for name in MISSION_METRIC_NAMES:
        existing = metrics_store.history(conn, "mission", name, limit=1)
        if existing:
            continue
        baseline = {
            "us_compute_share": 0.62,
            "china_compute_output": 0.34,
            "stratus_share_us_mil": 0.0,
        }[name]
        mid = metrics_store.record(
            conn, section="mission", name=name, value=baseline, unit="ratio"
        )
        written[name] = mid
    return written


def upsert_choke_point(
    conn: sqlite3.Connection,
    *,
    week: str,
    rank: int,
    title: str,
    note: str | None = None,
) -> int:
    if not 1 <= rank <= MAX_CHOKE_POINTS_PER_WEEK:
        raise ValueError(f"rank must be 1..{MAX_CHOKE_POINTS_PER_WEEK}")
    if not title.strip():
        raise ValueError("empty title")
    now = time.time()
    row = conn.execute(
        "SELECT id FROM choke_points WHERE week = ? AND rank = ?", (week, rank)
    ).fetchone()
    if row:
        conn.execute(
            "UPDATE choke_points SET title=?, note=?, recorded_at=? WHERE id=?",
            (title, note, now, row["id"]),
        )
        return int(row["id"])
    cur = conn.execute(
        "INSERT INTO choke_points(week, rank, title, note, recorded_at) VALUES(?, ?, ?, ?, ?)",
        (week, rank, title, note, now),
    )
    return int(cur.lastrowid)


def list_choke_points(conn: sqlite3.Connection, week: str) -> list[ChokePoint]:
    rows = conn.execute(
        "SELECT rank, title, note, recorded_at FROM choke_points WHERE week = ? ORDER BY rank ASC",
        (week,),
    ).fetchall()
    return [
        ChokePoint(rank=r["rank"], title=r["title"], note=r["note"], recorded_at=r["recorded_at"])
        for r in rows
    ]
