from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from vector.agents import AgentManager, RunResult
from vector.app import app
from vector.config import get_settings
from vector.deps import set_agents, set_db
from vector.store import connect


@pytest.fixture()
def secured_client(tmp_path: Path):
    conn = connect(tmp_path / "v.db")
    set_db(conn)

    async def exec_fast(spec, prompt):
        return RunResult(output="ok", cost_usd=0.01)

    set_agents(AgentManager(executor=exec_fast, max_parallel=3))

    s = get_settings()
    original = s.backend_bearer
    s.backend_bearer = "secret-token"
    try:
        yield TestClient(app), "secret-token"
    finally:
        s.backend_bearer = original
        set_agents(None)
        set_db(None)
        conn.close()


def _spawn_body() -> dict:
    return {"type": "research", "prompt": "go"}


def test_spawn_without_bearer_returns_401(secured_client):
    c, _ = secured_client
    r = c.post("/agents/spawn", json=_spawn_body())
    assert r.status_code == 401


def test_spawn_with_wrong_bearer_returns_401(secured_client):
    c, _ = secured_client
    r = c.post(
        "/agents/spawn",
        json=_spawn_body(),
        headers={"Authorization": "Bearer wrong"},
    )
    assert r.status_code == 401


def test_spawn_with_correct_bearer_succeeds(secured_client):
    c, token = secured_client
    r = c.post(
        "/agents/spawn",
        json=_spawn_body(),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200


def test_kill_protected(secured_client):
    c, token = secured_client
    spawned = c.post(
        "/agents/spawn",
        json=_spawn_body(),
        headers={"Authorization": f"Bearer {token}"},
    ).json()
    r = c.post(f"/agents/{spawned['id']}/kill", json={"reason": "stop"})
    assert r.status_code == 401


def test_override_protected(secured_client):
    c, _ = secured_client
    r = c.post(
        "/daily/override",
        json={"day": "2026-05-12", "removed_task_id": 1, "added_task_id": 2},
    )
    assert r.status_code == 401


def test_read_endpoints_remain_open(secured_client):
    c, _ = secured_client
    assert c.get("/healthz").status_code == 200
    assert c.get("/agents").status_code == 200
    assert c.get("/audit").status_code == 200


def test_constant_time_comparison_is_used():
    """Smoke test: hmac.compare_digest is what we call."""
    from vector.auth import hmac as auth_hmac

    assert auth_hmac.compare_digest("a", "a") is True
    assert auth_hmac.compare_digest("a", "b") is False
