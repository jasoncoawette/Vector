from __future__ import annotations

import random
import sqlite3
import time
from dataclasses import dataclass

from .routing import (
    THRESH_HARD,
    THRESH_SIMPLE,
    TIER_MODELS,
    RoutingDecision,
    Tier,
    complexity_score,
    heuristic_route,
)

WARMUP_TRIALS = 50
TIER_SCORE_BIAS: dict[Tier, float] = {
    Tier.HAIKU: 0.6,
    Tier.SONNET: 0.5,
    Tier.OPUS: 0.4,
}


@dataclass
class TierStats:
    tier: Tier
    alpha: float
    beta: float
    trials: int

    def mean(self) -> float:
        return self.alpha / (self.alpha + self.beta)


def _now() -> float:
    return time.time()


def _ensure_rows(conn: sqlite3.Connection) -> None:
    for tier in Tier:
        conn.execute(
            "INSERT OR IGNORE INTO routing_bandit(tier, alpha, beta, trials, updated_at) "
            "VALUES(?, 1.0, 1.0, 0, ?)",
            (tier.value, _now()),
        )


def load_stats(conn: sqlite3.Connection) -> dict[Tier, TierStats]:
    _ensure_rows(conn)
    rows = conn.execute("SELECT tier, alpha, beta, trials FROM routing_bandit").fetchall()
    out: dict[Tier, TierStats] = {}
    for r in rows:
        try:
            t = Tier(r["tier"])
        except ValueError:
            continue
        out[t] = TierStats(tier=t, alpha=r["alpha"], beta=r["beta"], trials=r["trials"])
    return out


def _candidate_tiers(score: float) -> list[Tier]:
    """Allow the bandit to drift one tier in either direction from the
    heuristic, but never cross both thresholds."""
    if score < THRESH_SIMPLE:
        return [Tier.HAIKU, Tier.SONNET]
    if score < THRESH_HARD:
        return [Tier.HAIKU, Tier.SONNET, Tier.OPUS]
    return [Tier.SONNET, Tier.OPUS]


def route(
    conn: sqlite3.Connection,
    prompt: str,
    *,
    agent_type: str | None = None,
    rng: random.Random | None = None,
) -> RoutingDecision:
    score, feats = complexity_score(prompt, agent_type=agent_type)
    stats = load_stats(conn)
    total_trials = sum(s.trials for s in stats.values())
    if total_trials < WARMUP_TRIALS:
        decision = heuristic_route(prompt, agent_type=agent_type)
        decision.log_id = log_decision(conn, decision, agent_type)
        return decision

    r = rng or random
    samples: dict[Tier, float] = {}
    for tier in _candidate_tiers(score):
        s = stats[tier]
        sample = r.betavariate(s.alpha, s.beta)
        bias = TIER_SCORE_BIAS[tier]
        samples[tier] = sample + (score - bias)
    picked = max(samples, key=samples.get)
    decision = RoutingDecision(
        tier=picked, model=TIER_MODELS[picked], score=score, features=feats, source="bandit"
    )
    decision.log_id = log_decision(conn, decision, agent_type)
    return decision


def record_outcome(
    conn: sqlite3.Connection,
    decision: RoutingDecision,
    *,
    success: bool,
    cost_usd: float = 0.0,
) -> None:
    _ensure_rows(conn)
    delta_a = 1.0 if success else 0.0
    delta_b = 0.0 if success else 1.0
    conn.execute(
        """
        UPDATE routing_bandit
        SET alpha = alpha + ?, beta = beta + ?, trials = trials + 1, updated_at = ?
        WHERE tier = ?
        """,
        (delta_a, delta_b, _now(), decision.tier.value),
    )
    if decision.log_id is not None:
        conn.execute(
            "UPDATE routing_log SET outcome = ?, cost_usd = ? WHERE id = ?",
            (1 if success else 0, cost_usd, decision.log_id),
        )


def log_decision(
    conn: sqlite3.Connection,
    decision: RoutingDecision,
    agent_type: str | None,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO routing_log(ts, agent_type, tier, model, score, source)
        VALUES(?, ?, ?, ?, ?, ?)
        """,
        (
            _now(),
            agent_type,
            decision.tier.value,
            decision.model,
            decision.score,
            decision.source,
        ),
    )
    return int(cur.lastrowid)
