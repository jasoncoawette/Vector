from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from vector.agents import AgentManager, RunResult
from vector.app import app
from vector.deps import set_agents


@pytest.fixture()
def client():
    async def exec_fast(spec, prompt):
        return RunResult(output=f"done: {prompt}", cost_usd=0.05)

    mgr = AgentManager(executor=exec_fast, max_parallel=3)
    set_agents(mgr)
    c = TestClient(app)
    yield c, mgr
    set_agents(None)


def _spawn(c: TestClient, **kw):
    body = {"type": "research", "prompt": "search AFWERX SBIR"}
    body.update(kw)
    return c.post("/agents/spawn", json=body)


def test_spawn_returns_summary(client):
    c, _ = client
    r = _spawn(c)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] in ("queued", "running", "done")
    assert body["type"] == "research"


def test_spawn_rejects_invalid_type(client):
    c, _ = client
    r = _spawn(c, type="cyberweapon")
    assert r.status_code == 422


def test_spawn_rejects_empty_prompt(client):
    c, _ = client
    r = _spawn(c, prompt="")
    assert r.status_code == 422


def test_spawn_rejects_huge_cost_cap(client):
    c, _ = client
    r = _spawn(c, cost_cap_usd=999.0)
    assert r.status_code == 422


def test_list_agents(client):
    c, _ = client
    _spawn(c)
    _spawn(c, type="code", prompt="touch", files=["/x.py"])
    r = c.get("/agents")
    assert r.status_code == 200
    assert len(r.json()["runs"]) >= 2


def test_get_unknown_returns_404(client):
    c, _ = client
    assert c.get("/agents/nope").status_code == 404


def test_kill_run(client):
    async def exec_slow(spec, prompt):
        await asyncio.sleep(10)
        return RunResult()

    mgr = AgentManager(executor=exec_slow, max_parallel=3)
    set_agents(mgr)
    try:
        c = TestClient(app)
        spawned = _spawn(c).json()
        run_id = spawned["id"]
        r = c.post(f"/agents/{run_id}/kill", json={"reason": "off topic"})
        assert r.status_code == 200
        assert r.json()["killed"] is True
        report = c.get(f"/agents/{run_id}/report").json()
        assert "killed" in report["text"].lower()
    finally:
        set_agents(None)


def test_report_known_run(client):
    c, mgr = client
    spawned = _spawn(c).json()
    # Wait briefly for completion
    for _ in range(50):
        run = mgr.get(spawned["id"])
        if run and run.status.value == "done":
            break
        import time

        time.sleep(0.02)
    r = c.get(f"/agents/{spawned['id']}/report")
    assert r.status_code == 200
    assert "agent" in r.json()["text"].lower()
