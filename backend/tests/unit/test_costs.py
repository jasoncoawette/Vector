from __future__ import annotations

import time
from pathlib import Path

import pytest

from vector.store import connect
from vector.store import runs as runs_store
from vector.voice.costs import _start_of_today_utc, summarize


@pytest.fixture()
def conn(tmp_path: Path):
    c = connect(tmp_path / "v.db")
    yield c
    c.close()


def _put_run(conn, id_: str, type_: str, cost: float, queued_at: float) -> None:
    runs_store.upsert_from_summary(
        conn,
        {
            "id": id_,
            "trace_id": None,
            "type": type_,
            "prompt": "x",
            "files": [],
            "status": "done",
            "output": "",
            "error": "",
            "cost_usd": cost,
            "fallback_used": False,
            "attempts_used": 1,
            "max_attempts": 1,
            "last_verifier_reason": None,
        },
        queued_at=queued_at,
    )


def _put_routing(conn, tier: str, cost: float, ts: float) -> None:
    conn.execute(
        "INSERT INTO routing_log(ts, tier, model, score, source, cost_usd) "
        "VALUES(?, ?, ?, ?, ?, ?)",
        (ts, tier, f"claude-{tier}", 0.5, "bandit", cost),
    )


def test_today_includes_only_runs_from_today(conn):
    now = time.time()
    start_today = _start_of_today_utc(now)
    _put_run(conn, "a", "code", 0.10, start_today + 1)
    _put_run(conn, "b", "research", 0.05, start_today - 86400)
    s = summarize(conn, now=now)
    assert s.today_usd == pytest.approx(0.10)
    assert s.today_runs == 1


def test_week_total_spans_7_days(conn):
    now = time.time()
    start_today = _start_of_today_utc(now)
    _put_run(conn, "a", "code", 0.10, start_today + 1)
    _put_run(conn, "b", "research", 0.05, start_today - 3 * 86400)
    _put_run(conn, "c", "writer", 0.01, start_today - 10 * 86400)
    s = summarize(conn, now=now)
    assert s.week_usd == pytest.approx(0.15)
    assert s.week_runs == 2


def test_month_total_spans_30_days(conn):
    now = time.time()
    start_today = _start_of_today_utc(now)
    _put_run(conn, "a", "code", 0.10, start_today + 1)
    _put_run(conn, "b", "research", 0.05, start_today - 20 * 86400)
    _put_run(conn, "c", "writer", 0.01, start_today - 40 * 86400)
    s = summarize(conn, now=now)
    assert s.month_usd == pytest.approx(0.15)


def test_budget_flag(conn):
    now = time.time()
    _put_run(conn, "a", "code", 0.30, _start_of_today_utc(now) + 1)
    under = summarize(conn, now=now, daily_budget_usd=1.0)
    over = summarize(conn, now=now, daily_budget_usd=0.20)
    assert under.over_budget_today is False
    assert over.over_budget_today is True


def test_zero_budget_disables_flag(conn):
    now = time.time()
    _put_run(conn, "a", "code", 100.0, _start_of_today_utc(now) + 1)
    s = summarize(conn, now=now, daily_budget_usd=0.0)
    assert s.over_budget_today is False


def test_daily_rollup_groups_by_type(conn):
    now = time.time()
    start_today = _start_of_today_utc(now)
    _put_run(conn, "a", "code", 0.10, start_today + 1)
    _put_run(conn, "b", "code", 0.05, start_today + 2)
    _put_run(conn, "c", "research", 0.02, start_today + 3)
    s = summarize(conn, now=now)
    today = next(d for d in s.daily if d.runs > 0)
    assert today.by_type["code"] == pytest.approx(0.15)
    assert today.by_type["research"] == pytest.approx(0.02)


def test_history_days_clamped(conn):
    now = time.time()
    s = summarize(conn, now=now, history_days=999)
    # Should not crash; daily is empty when there's no data, that's fine.
    assert isinstance(s.daily, list)


def test_by_tier_pulled_from_routing_log(conn):
    now = time.time()
    _put_routing(conn, "haiku", 0.001, now - 100)
    _put_routing(conn, "haiku", 0.002, now - 50)
    _put_routing(conn, "sonnet", 0.01, now - 10)
    s = summarize(conn, now=now)
    by_tier = {t.tier: t for t in s.by_tier}
    assert by_tier["haiku"].decisions == 2
    assert by_tier["haiku"].total_usd == pytest.approx(0.003)
    assert by_tier["sonnet"].total_usd == pytest.approx(0.01)


def test_costs_endpoint_returns_payload(tmp_path: Path):
    from fastapi.testclient import TestClient

    from vector.app import app
    from vector.deps import set_db

    conn = connect(tmp_path / "v.db")
    set_db(conn)
    try:
        _put_run(conn, "a", "code", 0.10, _start_of_today_utc() + 1)
        c = TestClient(app)
        body = c.get("/costs").json()
        assert "today_usd" in body
        assert body["today_runs"] == 1
        assert body["today_usd"] == pytest.approx(0.10)
        assert isinstance(body["daily"], list)
        assert isinstance(body["by_tier"], list)
    finally:
        set_db(None)
        conn.close()
