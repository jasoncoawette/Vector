from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from vector.agents import AgentManager, RunResult
from vector.app import app
from vector.deps import set_agents, set_db
from vector.store import connect
from vector.store import runs as runs_store


@pytest.fixture()
def client(tmp_path: Path):
    conn = connect(tmp_path / "v.db")
    set_db(conn)

    def _persist(summary, queued_at):
        runs_store.upsert_from_summary(conn, summary, queued_at=queued_at)

    async def exec_(spec, prompt):
        return RunResult(output=f"done: {prompt}", cost_usd=0.02)

    set_agents(AgentManager(executor=exec_, max_parallel=2, persist=_persist))
    yield TestClient(app), conn
    set_agents(None)
    set_db(None)
    conn.close()


def test_list_runs_after_spawn(client):
    c, _ = client
    r = c.post("/agents/spawn", json={"type": "research", "prompt": "go"})
    run_id = r.json()["id"]
    import time

    for _ in range(50):
        time.sleep(0.01)
        rows = c.get("/runs").json()["runs"]
        if any(row["id"] == run_id and row["status"] == "done" for row in rows):
            break
    rows = c.get("/runs").json()["runs"]
    assert any(row["id"] == run_id for row in rows)


def test_get_run_by_id(client):
    c, _ = client
    r = c.post("/agents/spawn", json={"type": "research", "prompt": "go"})
    run_id = r.json()["id"]
    res = c.get(f"/runs/{run_id}")
    assert res.status_code == 200
    body = res.json()
    assert body["id"] == run_id


def test_get_unknown_run_404(client):
    c, _ = client
    assert c.get("/runs/nope").status_code == 404


def test_status_filter(client):
    c, _ = client
    c.post("/agents/spawn", json={"type": "research", "prompt": "a"})
    c.post("/agents/spawn", json={"type": "research", "prompt": "b"})
    import time

    for _ in range(50):
        time.sleep(0.01)
        rows = c.get("/runs?status=done").json()["runs"]
        if len(rows) >= 2:
            break
    rows = c.get("/runs?status=done").json()["runs"]
    assert all(r["status"] == "done" for r in rows)


def test_runs_survives_recreated_manager(client):
    """Spawn, persist, blow away the manager, the row should still
    be in /runs."""
    c, conn = client
    r = c.post("/agents/spawn", json={"type": "research", "prompt": "remembered"})
    run_id = r.json()["id"]
    import time

    for _ in range(50):
        time.sleep(0.01)
        if runs_store.get(conn, run_id) and runs_store.get(conn, run_id).status == "done":
            break

    # "Restart" the manager — equivalent to a backend process restart.
    set_agents(None)
    rows = c.get("/runs").json()["runs"]
    assert any(row["id"] == run_id for row in rows)


def test_startup_marks_running_rows_as_interrupted(tmp_path: Path):
    """Simulate a crash: write a row in 'running' state then restart."""
    db_path = tmp_path / "v.db"
    conn = connect(db_path)
    runs_store.upsert_from_summary(
        conn,
        {
            "id": "crashed",
            "trace_id": "x",
            "type": "code",
            "prompt": "stuff",
            "files": [],
            "status": "running",
            "output": "",
            "error": "",
            "cost_usd": 0.0,
            "fallback_used": False,
            "attempts_used": 1,
            "max_attempts": 1,
            "last_verifier_reason": None,
        },
    )
    conn.close()

    # Reopen and run the startup recovery sweep directly.
    conn2 = connect(db_path)
    n = runs_store.mark_interrupted_on_startup(conn2)
    assert n == 1
    row = runs_store.get(conn2, "crashed")
    assert row.status == "interrupted"
    conn2.close()
