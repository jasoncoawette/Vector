from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from .bandit import load_stats
from .routing import Tier


@dataclass
class TierSummary:
    tier: str
    decisions: int
    successes: int
    failures: int
    pending: int
    mean_cost_usd: float
    success_rate: float
    alpha: float
    beta: float
    trials: int
    mean_reward: float


def per_tier_summary(conn: sqlite3.Connection) -> list[TierSummary]:
    rows = conn.execute(
        """
        SELECT
            tier,
            COUNT(*) AS decisions,
            SUM(CASE WHEN outcome = 1 THEN 1 ELSE 0 END) AS successes,
            SUM(CASE WHEN outcome = 0 THEN 1 ELSE 0 END) AS failures,
            SUM(CASE WHEN outcome IS NULL THEN 1 ELSE 0 END) AS pending,
            AVG(COALESCE(cost_usd, 0)) AS mean_cost
        FROM routing_log
        GROUP BY tier
        """
    ).fetchall()
    by_tier = {r["tier"]: r for r in rows}
    bandit_stats = load_stats(conn)

    out: list[TierSummary] = []
    for tier in Tier:
        r = by_tier.get(tier.value)
        decisions = int(r["decisions"]) if r else 0
        successes = int(r["successes"] or 0) if r else 0
        failures = int(r["failures"] or 0) if r else 0
        pending = int(r["pending"] or 0) if r else 0
        mean_cost = float(r["mean_cost"] or 0.0) if r else 0.0
        decided = successes + failures
        success_rate = successes / decided if decided else 0.0
        b = bandit_stats[tier]
        out.append(
            TierSummary(
                tier=tier.value,
                decisions=decisions,
                successes=successes,
                failures=failures,
                pending=pending,
                mean_cost_usd=mean_cost,
                success_rate=success_rate,
                alpha=b.alpha,
                beta=b.beta,
                trials=b.trials,
                mean_reward=b.mean(),
            )
        )
    return out


def recent_decisions(conn: sqlite3.Connection, *, limit: int = 100) -> list[dict]:
    limit = max(1, min(limit, 500))
    rows = conn.execute(
        """
        SELECT ts, agent_type, tier, model, score, source, outcome, cost_usd
        FROM routing_log ORDER BY ts DESC LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [
        {
            "ts": r["ts"],
            "agent_type": r["agent_type"],
            "tier": r["tier"],
            "model": r["model"],
            "score": r["score"],
            "source": r["source"],
            "outcome": r["outcome"],
            "cost_usd": r["cost_usd"],
        }
        for r in rows
    ]
