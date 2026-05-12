"""Cost rollups across runs, routing, and verifier overhead.

Sources of cost in Vector:
- runs.cost_usd — total cost recorded per agent run (includes verifier)
- routing_log.cost_usd — per-decision cost stamped via record_outcome

For rollups we use `runs` as the canonical billing surface because:
1. it's append-once per agent (no double-count from intermediate steps)
2. it includes the verifier overhead which routing_log doesn't see

routing_log gives tier-level breakdown that runs doesn't.
"""
from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class DailyCost:
    day: str  # ISO date in UTC
    total_usd: float
    runs: int
    by_type: dict[str, float]


@dataclass
class TierCost:
    tier: str
    decisions: int
    total_usd: float
    mean_usd: float


@dataclass
class CostSummary:
    today_usd: float
    today_runs: int
    week_usd: float
    week_runs: int
    month_usd: float
    month_runs: int
    daily: list[DailyCost]
    by_tier: list[TierCost]
    daily_budget_usd: float
    over_budget_today: bool


def _start_of_today_utc(now: float | None = None) -> float:
    t = now if now is not None else time.time()
    dt = datetime.fromtimestamp(t, tz=timezone.utc)
    midnight = dt.replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight.timestamp()


def summarize(
    conn: sqlite3.Connection,
    *,
    now: float | None = None,
    daily_budget_usd: float = 0.0,
    history_days: int = 14,
) -> CostSummary:
    current = now if now is not None else time.time()
    start_today = _start_of_today_utc(current)
    start_week = start_today - 6 * 86400  # last 7 days inclusive of today
    start_month = start_today - 29 * 86400

    today_row = conn.execute(
        "SELECT COUNT(*) AS n, COALESCE(SUM(cost_usd), 0) AS s FROM runs "
        "WHERE queued_at >= ?",
        (start_today,),
    ).fetchone()
    week_row = conn.execute(
        "SELECT COUNT(*) AS n, COALESCE(SUM(cost_usd), 0) AS s FROM runs "
        "WHERE queued_at >= ?",
        (start_week,),
    ).fetchone()
    month_row = conn.execute(
        "SELECT COUNT(*) AS n, COALESCE(SUM(cost_usd), 0) AS s FROM runs "
        "WHERE queued_at >= ?",
        (start_month,),
    ).fetchone()

    # Per-day rollup over history_days days.
    history_days = max(1, min(history_days, 90))
    earliest = start_today - (history_days - 1) * 86400
    rows = conn.execute(
        """
        SELECT
            CAST(strftime('%Y-%m-%d', queued_at, 'unixepoch') AS TEXT) AS d,
            COUNT(*) AS n,
            COALESCE(SUM(cost_usd), 0) AS s,
            type
        FROM runs
        WHERE queued_at >= ?
        GROUP BY d, type
        ORDER BY d ASC
        """,
        (earliest,),
    ).fetchall()
    per_day: dict[str, DailyCost] = {}
    for r in rows:
        day = r["d"]
        if day not in per_day:
            per_day[day] = DailyCost(day=day, total_usd=0.0, runs=0, by_type={})
        per_day[day].total_usd += float(r["s"] or 0.0)
        per_day[day].runs += int(r["n"] or 0)
        per_day[day].by_type[r["type"]] = (
            per_day[day].by_type.get(r["type"], 0.0) + float(r["s"] or 0.0)
        )

    # Per-tier rollup from routing_log.
    tier_rows = conn.execute(
        """
        SELECT tier,
               COUNT(*) AS n,
               COALESCE(SUM(cost_usd), 0) AS s
        FROM routing_log
        WHERE ts >= ? AND cost_usd IS NOT NULL
        GROUP BY tier
        """,
        (start_month,),
    ).fetchall()
    by_tier: list[TierCost] = []
    for r in tier_rows:
        n = int(r["n"] or 0)
        total = float(r["s"] or 0.0)
        by_tier.append(
            TierCost(
                tier=r["tier"],
                decisions=n,
                total_usd=total,
                mean_usd=(total / n) if n else 0.0,
            )
        )

    today_usd = float(today_row["s"] or 0.0)
    over_budget = bool(daily_budget_usd > 0 and today_usd > daily_budget_usd)

    return CostSummary(
        today_usd=today_usd,
        today_runs=int(today_row["n"] or 0),
        week_usd=float(week_row["s"] or 0.0),
        week_runs=int(week_row["n"] or 0),
        month_usd=float(month_row["s"] or 0.0),
        month_runs=int(month_row["n"] or 0),
        daily=sorted(per_day.values(), key=lambda d: d.day),
        by_tier=sorted(by_tier, key=lambda t: -t.total_usd),
        daily_budget_usd=daily_budget_usd,
        over_budget_today=over_budget,
    )
