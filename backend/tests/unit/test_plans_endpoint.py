from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from vector.agents import AgentManager, RunResult
from vector.app import app
from vector.deps import set_agents, set_db, set_plans
from vector.plans import PlanRunner
from vector.store import connect


@pytest.fixture()
def client(tmp_path: Path):
    conn = connect(tmp_path / "v.db", check_integrity=False)
    set_db(conn)

    async def exec_(spec, prompt):
        # Echo so substitution shows up in step 2's prompt.
        return RunResult(output=f"output-of:{prompt[:50]}", cost_usd=0.01)

    mgr = AgentManager(executor=exec_, max_parallel=4)
    set_agents(mgr)
    set_plans(PlanRunner(manager=mgr))

    yield TestClient(app), conn
    set_plans(None)
    set_agents(None)
    set_db(None)
    conn.close()


def _wait_for_status(c: TestClient, plan_id: str, target: str, max_s: float = 8.0):
    deadline = time.time() + max_s
    last = None
    while time.time() < deadline:
        last = c.get(f"/plans/{plan_id}").json()
        if last["status"] == target:
            return last
        time.sleep(0.02)
    return last


def test_post_plan_returns_run_immediately(client):
    c, _ = client
    r = c.post(
        "/plans",
        json={
            "goal": "test",
            "steps": [
                {"id": 1, "agent": "research", "prompt": "step 1"},
                {"id": 2, "agent": "writer", "prompt": "step 2", "depends_on": [1]},
            ],
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] in ("running", "done")
    assert body["plan"]["goal"] == "test"


def test_plan_runs_to_completion_in_background(client):
    c, _ = client
    plan_id = c.post(
        "/plans",
        json={
            "goal": "g",
            "steps": [{"id": 1, "agent": "research", "prompt": "do it"}],
        },
    ).json()["plan"]["id"]

    final = _wait_for_status(c, plan_id, "done")
    assert final["status"] == "done"
    assert final["steps"][0]["status"] == "done"
    assert final["steps"][0]["output"].startswith("output-of:")


def test_post_plan_rejects_cycle_400(client):
    c, _ = client
    r = c.post(
        "/plans",
        json={
            "goal": "bad",
            "steps": [
                {"id": 1, "agent": "code", "prompt": "x", "depends_on": [2]},
                {"id": 2, "agent": "code", "prompt": "y", "depends_on": [1]},
            ],
        },
    )
    assert r.status_code == 400
    assert "cycle" in r.json()["detail"]


def test_get_unknown_plan_404(client):
    c, _ = client
    assert c.get("/plans/nope").status_code == 404


def test_list_plans(client):
    c, _ = client
    c.post(
        "/plans",
        json={"goal": "g", "steps": [{"id": 1, "agent": "research", "prompt": "x"}]},
    )
    c.post(
        "/plans",
        json={"goal": "h", "steps": [{"id": 1, "agent": "research", "prompt": "y"}]},
    )
    body = c.get("/plans").json()
    assert len(body["plans"]) >= 2


def test_placeholder_substitution_via_http(client):
    c, _ = client
    plan_id = c.post(
        "/plans",
        json={
            "goal": "thread output",
            "steps": [
                {"id": 1, "agent": "research", "prompt": "do step 1"},
                {
                    "id": 2,
                    "agent": "writer",
                    "prompt": "use {{step_1.output}} downstream",
                    "depends_on": [1],
                },
            ],
        },
    ).json()["plan"]["id"]
    final = _wait_for_status(c, plan_id, "done")
    # Step 2's output was generated from the substituted prompt, which
    # contained step 1's output.
    step2_output = final["steps"][1]["output"]
    assert "output-of:" in step2_output
    # The substituted prompt should reference step 1's output text.
    assert "do step 1" in step2_output


def test_post_plan_requires_bearer_when_set(tmp_path: Path):
    from vector.config import get_settings

    conn = connect(tmp_path / "v.db", check_integrity=False)
    set_db(conn)

    async def exec_(spec, prompt):
        return RunResult(output="ok")

    mgr = AgentManager(executor=exec_, max_parallel=2)
    set_agents(mgr)
    set_plans(PlanRunner(manager=mgr))

    s = get_settings()
    original = s.backend_bearer
    s.backend_bearer = "test-bearer"
    try:
        c = TestClient(app)
        r = c.post(
            "/plans",
            json={"goal": "g", "steps": [{"id": 1, "agent": "research", "prompt": "x"}]},
        )
        assert r.status_code == 401
        r2 = c.post(
            "/plans",
            json={"goal": "g", "steps": [{"id": 1, "agent": "research", "prompt": "x"}]},
            headers={"Authorization": "Bearer test-bearer"},
        )
        assert r2.status_code == 200
    finally:
        s.backend_bearer = original
        set_plans(None)
        set_agents(None)
        set_db(None)
        conn.close()
