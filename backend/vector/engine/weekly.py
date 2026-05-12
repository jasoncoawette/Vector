from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta

from ..store import metrics as metrics_store
from . import mission as mission_eng


@dataclass
class WeeklySummary:
    week: str
    shipped: int
    slipped: int
    metric_deltas: dict[str, dict[str, float]]
    choke_points: list[str]
    text: str


def _week_bounds(now: datetime) -> tuple[float, float]:
    start = (now - timedelta(days=now.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    end = start + timedelta(days=7)
    return start.timestamp(), end.timestamp()


def _week_iso(now: datetime) -> str:
    iso = now.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def _count_picks(conn: sqlite3.Connection, start: float, end: float) -> tuple[int, int]:
    rows = conn.execute(
        """
        SELECT p.task_id, t.status FROM picks p
        JOIN tasks t ON p.task_id = t.id
        WHERE p.id IN (
            SELECT id FROM picks WHERE day BETWEEN ? AND ?
        )
        """,
        (
            datetime.fromtimestamp(start).date().isoformat(),
            datetime.fromtimestamp(end).date().isoformat(),
        ),
    ).fetchall()
    shipped = sum(1 for r in rows if r["status"] == "shipped")
    return shipped, max(0, len(rows) - shipped)


def _metric_delta(
    conn: sqlite3.Connection, section: str, name: str, start: float, end: float
) -> dict[str, float] | None:
    rows = conn.execute(
        """
        SELECT value, recorded_at FROM metrics
        WHERE section = ? AND name = ? AND recorded_at <= ?
        ORDER BY recorded_at DESC LIMIT 1
        """,
        (section, name, end),
    ).fetchall()
    if not rows:
        return None
    latest = rows[0]["value"]
    prior = conn.execute(
        """
        SELECT value FROM metrics
        WHERE section = ? AND name = ? AND recorded_at < ?
        ORDER BY recorded_at DESC LIMIT 1
        """,
        (section, name, start),
    ).fetchone()
    prior_v = prior["value"] if prior else latest
    return {"latest": latest, "prior": prior_v, "delta": latest - prior_v}


def render_weekly(conn: sqlite3.Connection, *, now: datetime, user: str = "Jason") -> WeeklySummary:
    start, end = _week_bounds(now)
    week_iso = _week_iso(now)
    shipped, slipped = _count_picks(conn, start, end)

    deltas: dict[str, dict[str, float]] = {}
    for name in mission_eng.MISSION_METRIC_NAMES:
        d = _metric_delta(conn, "mission", name, start, end)
        if d is not None:
            deltas[name] = d

    choke = [p.title for p in mission_eng.list_choke_points(conn, week_iso)]

    parts: list[str] = [f"Weekly review for {user}, {week_iso}."]
    total = shipped + slipped
    if total:
        parts.append(f"Shipped {shipped} of {total} picks.")
    else:
        parts.append("No picks logged this week.")

    if "us_compute_share" in deltas and "china_compute_output" in deltas:
        us_d = deltas["us_compute_share"]["delta"] * 100
        cn_d = deltas["china_compute_output"]["delta"] * 100
        direction = "widened" if us_d - cn_d > 0 else "narrowed"
        parts.append(
            f"US lead {direction} by {abs(us_d - cn_d):.1f} points this week."
        )

    if "stratus_share_us_mil" in deltas:
        s = deltas["stratus_share_us_mil"]
        parts.append(
            f"Stratus share of US mil compute at {s['latest'] * 100:.2f}%, "
            f"delta {s['delta'] * 100:+.2f}."
        )

    if choke:
        parts.append("Top choke points: " + "; ".join(choke) + ".")

    return WeeklySummary(
        week=week_iso,
        shipped=shipped,
        slipped=slipped,
        metric_deltas=deltas,
        choke_points=choke,
        text=" ".join(parts),
    )
