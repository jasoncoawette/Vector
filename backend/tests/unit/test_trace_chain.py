"""End-to-end: confirm a trace_id propagates from the FastAPI entry
point all the way down through audit + events + run summary."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from vector.agents import AgentManager, RunResult
from vector.app import app
from vector.deps import set_agents, set_db


@pytest.fixture()
def client(tmp_path: Path):
    from vector.store import connect

    conn = connect(tmp_path / "v.db")
    set_db(conn)

    async def exec_fast(spec, prompt):
        # Inside the executor the trace_id should be bound by the manager.
        from vector.tracing import current_trace_id

        return RunResult(output=f"trace_seen={current_trace_id()}", cost_usd=0.01)

    set_agents(AgentManager(executor=exec_fast, max_parallel=2))
    yield TestClient(app), conn
    set_agents(None)
    set_db(None)
    conn.close()


def test_spawn_assigns_trace_id_to_run(client):
    c, _ = client
    r = c.post("/agents/spawn", json={"type": "research", "prompt": "go"})
    summary = r.json()
    assert summary["trace_id"]
    assert len(summary["trace_id"]) >= 8


def test_trace_id_visible_inside_executor(client):
    c, _ = client
    r = c.post("/agents/spawn", json={"type": "research", "prompt": "go"})
    run_id = r.json()["id"]
    # Wait briefly for executor to run.
    import time

    for _ in range(30):
        s = c.get(f"/agents/{run_id}").json()
        if s["status"] == "done":
            break
        time.sleep(0.02)
    assert "trace_seen=" in s["output"]
    seen_trace = s["output"].split("trace_seen=", 1)[1]
    assert seen_trace == s["trace_id"]


def test_trace_endpoint_returns_chain(client):
    c, _ = client
    r = c.post("/agents/spawn", json={"type": "research", "prompt": "go"})
    summary = r.json()
    trace_id = summary["trace_id"]

    import time

    for _ in range(30):
        s = c.get(f"/agents/{summary['id']}").json()
        if s["status"] == "done":
            break
        time.sleep(0.02)

    chain = c.get(f"/trace/{trace_id}").json()
    assert chain["trace_id"] == trace_id
    # At minimum the spawn-request event landed.
    kinds = {e["kind"] for e in chain["events"]}
    assert "agent_spawn_request" in kinds


def test_events_endpoint_lists_recent(client):
    c, _ = client
    c.post("/agents/spawn", json={"type": "research", "prompt": "alpha"})
    c.post("/agents/spawn", json={"type": "research", "prompt": "beta"})
    body = c.get("/events?limit=50").json()
    assert "events" in body
    assert len(body["events"]) >= 2


def test_audit_log_includes_trace_id(client):
    from vector import audit

    c, conn = client
    audit.set_sink(conn)
    try:
        r = c.post("/agents/spawn", json={"type": "research", "prompt": "x"})
        trace_id = r.json()["trace_id"]
        rows = conn.execute(
            "SELECT trace_id FROM audit_log WHERE tool = 'agents.spawn'"
        ).fetchall()
        assert any(row["trace_id"] == trace_id for row in rows)
    finally:
        audit.set_sink(None)
