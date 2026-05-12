from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass

ALLOWED_SECTIONS = frozenset(
    {"stratus", "build", "network", "personal", "mission"}
)

STALE_AFTER_S: dict[str, int] = {
    "stratus": 31 * 24 * 3600,
    "build": 14 * 24 * 3600,
    "network": 7 * 24 * 3600,
    "personal": 2 * 24 * 3600,
    "mission": 7 * 24 * 3600,
}


@dataclass
class MetricPoint:
    section: str
    name: str
    value: float
    unit: str | None
    recorded_at: float


def record(
    conn: sqlite3.Connection,
    *,
    section: str,
    name: str,
    value: float,
    unit: str | None = None,
) -> int:
    if section not in ALLOWED_SECTIONS:
        raise ValueError(f"unknown section: {section}")
    if not name.strip():
        raise ValueError("empty metric name")
    cur = conn.execute(
        "INSERT INTO metrics(section, name, value, unit, recorded_at) VALUES(?, ?, ?, ?, ?)",
        (section, name, float(value), unit, time.time()),
    )
    return int(cur.lastrowid)


def latest(conn: sqlite3.Connection, section: str | None = None) -> list[MetricPoint]:
    if section is not None and section not in ALLOWED_SECTIONS:
        raise ValueError(f"unknown section: {section}")
    if section is None:
        rows = conn.execute(
            """
            SELECT section, name, value, unit, recorded_at
            FROM metrics m
            WHERE recorded_at = (
                SELECT MAX(recorded_at) FROM metrics
                WHERE section = m.section AND name = m.name
            )
            ORDER BY section, name
            """
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT section, name, value, unit, recorded_at
            FROM metrics m
            WHERE section = ? AND recorded_at = (
                SELECT MAX(recorded_at) FROM metrics
                WHERE section = m.section AND name = m.name
            )
            ORDER BY name
            """,
            (section,),
        ).fetchall()
    return [
        MetricPoint(
            section=r["section"],
            name=r["name"],
            value=r["value"],
            unit=r["unit"],
            recorded_at=r["recorded_at"],
        )
        for r in rows
    ]


def is_stale(point: MetricPoint, *, now: float | None = None) -> bool:
    horizon = STALE_AFTER_S.get(point.section, 7 * 24 * 3600)
    return (now or time.time()) - point.recorded_at > horizon


def history(
    conn: sqlite3.Connection, section: str, name: str, limit: int = 90
) -> list[MetricPoint]:
    if section not in ALLOWED_SECTIONS:
        raise ValueError(f"unknown section: {section}")
    rows = conn.execute(
        """
        SELECT section, name, value, unit, recorded_at FROM metrics
        WHERE section = ? AND name = ?
        ORDER BY recorded_at DESC LIMIT ?
        """,
        (section, name, max(1, min(limit, 1000))),
    ).fetchall()
    return [
        MetricPoint(
            section=r["section"],
            name=r["name"],
            value=r["value"],
            unit=r["unit"],
            recorded_at=r["recorded_at"],
        )
        for r in rows
    ]
