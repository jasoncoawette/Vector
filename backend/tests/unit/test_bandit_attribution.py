from __future__ import annotations

import random
from pathlib import Path

import pytest

from vector.store import connect
from vector.voice import bandit


@pytest.fixture()
def conn(tmp_path: Path):
    c = connect(tmp_path / "v.db")
    yield c
    c.close()


def test_decision_carries_log_id(conn):
    d = bandit.route(conn, "rename a var")
    assert d.log_id is not None
    assert d.log_id > 0


def test_outcome_updates_matching_row_not_latest(conn):
    """Two concurrent decisions for the same tier must each update
    their own row, not the latest-pending row."""
    rng = random.Random(0)
    # Burn through warmup so the bandit can be exercised directly.
    for _ in range(bandit.WARMUP_TRIALS):
        d = bandit.route(conn, "ping", rng=rng)
        bandit.record_outcome(conn, d, success=True, cost_usd=0.001)

    a = bandit.route(conn, "first task A", rng=rng)
    b = bandit.route(conn, "second task B", rng=rng)
    assert a.log_id != b.log_id

    # Record outcomes in reverse order.
    bandit.record_outcome(conn, b, success=False, cost_usd=0.20)
    bandit.record_outcome(conn, a, success=True, cost_usd=0.05)

    row_a = conn.execute(
        "SELECT outcome, cost_usd FROM routing_log WHERE id = ?", (a.log_id,)
    ).fetchone()
    row_b = conn.execute(
        "SELECT outcome, cost_usd FROM routing_log WHERE id = ?", (b.log_id,)
    ).fetchone()

    assert row_a["outcome"] == 1
    assert row_a["cost_usd"] == pytest.approx(0.05)
    assert row_b["outcome"] == 0
    assert row_b["cost_usd"] == pytest.approx(0.20)


def test_outcome_without_log_id_still_updates_priors(conn):
    """Backwards-compat: hand-crafted decisions without log_id still
    update the bandit table (priors only — no log row to touch)."""
    from vector.voice.routing import RoutingDecision, Tier, TIER_MODELS

    fake = RoutingDecision(
        tier=Tier.SONNET,
        model=TIER_MODELS[Tier.SONNET],
        score=0.5,
        features={},
        source="override",
    )
    bandit.record_outcome(conn, fake, success=True)
    stats = bandit.load_stats(conn)
    assert stats[Tier.SONNET].alpha > 1.0
