from __future__ import annotations

import random
from pathlib import Path

import pytest

from vector.store import connect
from vector.voice import bandit
from vector.voice.routing import Tier


@pytest.fixture()
def conn(tmp_path: Path):
    c = connect(tmp_path / "v.db")
    yield c
    c.close()


def test_warmup_uses_heuristic(conn):
    decision = bandit.route(conn, "rename a variable")
    assert decision.source == "heuristic"
    assert decision.tier == Tier.HAIKU


def test_bandit_kicks_in_after_warmup(conn):
    for _ in range(bandit.WARMUP_TRIALS):
        d = bandit.route(conn, "ping")
        bandit.record_outcome(conn, d, success=True, cost_usd=0.001)
    after = bandit.route(conn, "ping", rng=random.Random(0))
    assert after.source == "bandit"


def test_outcome_updates_alpha_and_beta(conn):
    d = bandit.route(conn, "show status")
    bandit.record_outcome(conn, d, success=True)
    stats = bandit.load_stats(conn)
    assert stats[d.tier].alpha > 1.0
    assert stats[d.tier].trials == 1
    bandit.record_outcome(conn, d, success=False)
    stats2 = bandit.load_stats(conn)
    assert stats2[d.tier].beta > 1.0


def test_routing_log_persists(conn):
    bandit.route(conn, "anything")
    rows = conn.execute("SELECT count(*) AS n FROM routing_log").fetchone()
    assert rows["n"] == 1


def test_candidate_tiers_for_low_score():
    cands = bandit._candidate_tiers(0.05)
    assert Tier.HAIKU in cands
    assert Tier.OPUS not in cands


def test_candidate_tiers_for_high_score():
    cands = bandit._candidate_tiers(0.9)
    assert Tier.OPUS in cands
    assert Tier.HAIKU not in cands


def test_bandit_drifts_to_winning_tier(conn):
    """After many successes on Sonnet and failures on Haiku for
    medium-complexity prompts, the bandit should prefer Sonnet."""
    rng = random.Random(42)
    for _ in range(60):
        d = bandit.route(conn, "implement a parser", rng=rng)
        success = d.tier == Tier.SONNET
        bandit.record_outcome(conn, d, success=success, cost_usd=0.01)
    counts: dict[Tier, int] = {}
    for _ in range(50):
        d = bandit.route(conn, "implement a parser", rng=rng)
        counts[d.tier] = counts.get(d.tier, 0) + 1
    assert counts.get(Tier.SONNET, 0) >= counts.get(Tier.HAIKU, 0)
