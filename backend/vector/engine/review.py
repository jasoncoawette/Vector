from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass

from ..store import tasks as tasks_repo


@dataclass
class Review:
    day: str
    shipped_ids: list[int]
    slipped_ids: list[int]
    note: str | None = None


def _day_picks(conn: sqlite3.Connection, day: str) -> list[int]:
    rows = conn.execute(
        "SELECT task_id FROM picks WHERE day = ? ORDER BY rank ASC", (day,)
    ).fetchall()
    return [r["task_id"] for r in rows]


def record_review(
    conn: sqlite3.Connection,
    *,
    day: str,
    shipped_ids: list[int],
    note: str | None = None,
) -> Review:
    all_ids = _day_picks(conn, day)
    shipped_set = {tid for tid in shipped_ids if tid in all_ids}
    slipped = [tid for tid in all_ids if tid not in shipped_set]

    for tid in shipped_set:
        tasks_repo.mark_shipped(conn, tid)

    conn.execute(
        """
        INSERT INTO reviews(day, shipped_ids, slipped_ids, note, recorded_at)
        VALUES(?, ?, ?, ?, ?)
        ON CONFLICT(day) DO UPDATE SET
            shipped_ids=excluded.shipped_ids,
            slipped_ids=excluded.slipped_ids,
            note=excluded.note,
            recorded_at=excluded.recorded_at
        """,
        (
            day,
            json.dumps(sorted(shipped_set)),
            json.dumps(slipped),
            note,
            time.time(),
        ),
    )
    return Review(day=day, shipped_ids=sorted(shipped_set), slipped_ids=slipped, note=note)


def render_review(review: Review, conn: sqlite3.Connection) -> str:
    if not review.shipped_ids and not review.slipped_ids:
        return f"No picks logged for {review.day}."
    parts = [f"Review for {review.day}."]
    parts.append(
        f"Shipped {len(review.shipped_ids)} of {len(review.shipped_ids) + len(review.slipped_ids)}."
    )
    for tid in review.shipped_ids:
        t = tasks_repo.get(conn, tid)
        if t:
            parts.append(f"Done: {t.title}.")
    for tid in review.slipped_ids:
        t = tasks_repo.get(conn, tid)
        if t:
            parts.append(f"Slipped: {t.title}.")
    if review.note:
        parts.append(f"Note: {review.note}")
    return " ".join(parts)
