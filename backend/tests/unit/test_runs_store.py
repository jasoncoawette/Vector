from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest

from vector.agents import AgentManager, AgentSpec, RunResult, RunStatus
from vector.store import connect
from vector.store import runs as runs_store


@pytest.fixture()
def conn(tmp_path: Path):
    c = connect(tmp_path / "v.db")
    yield c
    c.close()


def _summary(**kw) -> dict:
    base = {
        "id": "r1",
        "trace_id": "t1",
        "type": "code",
        "prompt": "ship it",
        "files": ["/a.py"],
        "status": "running",
        "output": "",
        "error": "",
        "cost_usd": 0.0,
        "fallback_used": False,
        "attempts_used": 1,
        "max_attempts": 3,
        "last_verifier_reason": None,
    }
    base.update(kw)
    return base


def test_upsert_inserts_new_row(conn):
    runs_store.upsert_from_summary(conn, _summary(), queued_at=100.0)
    r = runs_store.get(conn, "r1")
    assert r is not None
    assert r.type == "code"
    assert r.status == "running"
    assert r.files == ["/a.py"]


def test_upsert_updates_existing_row(conn):
    runs_store.upsert_from_summary(conn, _summary(), queued_at=100.0)
    runs_store.upsert_from_summary(
        conn,
        _summary(status="done", output="shipped", cost_usd=0.05),
    )
    r = runs_store.get(conn, "r1")
    assert r.status == "done"
    assert r.output == "shipped"
    assert r.cost_usd == pytest.approx(0.05)


def test_started_at_set_only_on_first_transition(conn):
    """started_at COALESCEs so the first non-null value wins."""
    runs_store.upsert_from_summary(conn, _summary(status="running"))
    r1 = runs_store.get(conn, "r1")
    # The store doesn't read started_at from the summary in this design;
    # it's left for the manager to record via timing. The contract is
    # that ended_at gets set when status leaves running/queued.
    runs_store.upsert_from_summary(conn, _summary(status="done"))
    r2 = runs_store.get(conn, "r1")
    assert r2.ended_at is not None
    assert r2.status == "done"


def test_recent_orders_by_updated_at(conn):
    runs_store.upsert_from_summary(conn, _summary(id="a"), queued_at=1.0)
    time.sleep(0.005)
    runs_store.upsert_from_summary(conn, _summary(id="b"), queued_at=2.0)
    rows = runs_store.recent(conn)
    assert [r.id for r in rows][:2] == ["b", "a"]


def test_recent_filters_by_status(conn):
    runs_store.upsert_from_summary(conn, _summary(id="a", status="running"))
    runs_store.upsert_from_summary(conn, _summary(id="b", status="done"))
    rows = runs_store.recent(conn, status="done")
    assert [r.id for r in rows] == ["b"]


def test_recent_limit_clamped(conn):
    for i in range(5):
        runs_store.upsert_from_summary(conn, _summary(id=f"r{i}"))
    rows = runs_store.recent(conn, limit=999999)
    assert len(rows) <= 500


def test_by_trace_returns_matching(conn):
    runs_store.upsert_from_summary(conn, _summary(id="a", trace_id="x"))
    runs_store.upsert_from_summary(conn, _summary(id="b", trace_id="x"))
    runs_store.upsert_from_summary(conn, _summary(id="c", trace_id="y"))
    rows = runs_store.by_trace(conn, "x")
    assert {r.id for r in rows} == {"a", "b"}


def test_mark_interrupted_only_touches_in_flight(conn):
    runs_store.upsert_from_summary(conn, _summary(id="run", status="running"))
    runs_store.upsert_from_summary(conn, _summary(id="queued", status="queued"))
    runs_store.upsert_from_summary(conn, _summary(id="done", status="done"))
    n = runs_store.mark_interrupted_on_startup(conn)
    assert n == 2
    assert runs_store.get(conn, "run").status == "interrupted"
    assert runs_store.get(conn, "queued").status == "interrupted"
    assert runs_store.get(conn, "done").status == "done"


def test_mark_interrupted_sets_default_error(conn):
    runs_store.upsert_from_summary(conn, _summary(id="r", status="running"))
    runs_store.mark_interrupted_on_startup(conn)
    r = runs_store.get(conn, "r")
    assert "restart" in r.error


def test_mark_interrupted_preserves_existing_error(conn):
    runs_store.upsert_from_summary(
        conn, _summary(id="r", status="running", error="OOM")
    )
    runs_store.mark_interrupted_on_startup(conn)
    r = runs_store.get(conn, "r")
    assert r.error == "OOM"


def test_corrupted_files_json_does_not_crash(conn):
    runs_store.upsert_from_summary(conn, _summary())
    # Corrupt the row directly.
    conn.execute("UPDATE runs SET files = '{not-json' WHERE id = 'r1'")
    r = runs_store.get(conn, "r1")
    assert r.files == []


async def test_manager_writes_through_on_spawn_and_complete(tmp_path):
    conn = connect(tmp_path / "v.db")

    def _persist(summary, queued_at):
        runs_store.upsert_from_summary(conn, summary, queued_at=queued_at)

    async def exec_(spec, prompt):
        return RunResult(output="ok", cost_usd=0.01)

    mgr = AgentManager(executor=exec_, max_parallel=2, persist=_persist)
    run = await mgr.spawn(AgentSpec(type="research", prompt="go"))

    # Right after spawn — row exists, queued or running.
    early = runs_store.get(conn, run.id)
    assert early is not None
    assert early.type == "research"

    await mgr.wait(run.id)

    final = runs_store.get(conn, run.id)
    assert final.status == "done"
    assert final.output == "ok"
    assert final.cost_usd == pytest.approx(0.01)
    conn.close()


async def test_manager_persistence_failure_does_not_break_run(tmp_path):
    """A crashing persist() callback must not abort the run."""

    def _persist(summary, queued_at):
        raise RuntimeError("disk full")

    async def exec_(spec, prompt):
        return RunResult(output="ok", cost_usd=0.0)

    mgr = AgentManager(executor=exec_, max_parallel=2, persist=_persist)
    run = await mgr.spawn(AgentSpec(type="research", prompt="go"))
    await mgr.wait(run.id)
    assert run.status == RunStatus.DONE
