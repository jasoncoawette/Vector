from __future__ import annotations

import asyncio

import pytest

from vector.agents import AgentManager, AgentSpec, RunResult, RunStatus
from vector.agents.auto_security import register_auto_security
from vector.hooks import HookRegistry


async def test_code_completion_spawns_security():
    seen_types: list[str] = []

    async def exec_(spec, prompt):
        seen_types.append(spec.type)
        return RunResult(output=f"{spec.type} ok", cost_usd=0.01)

    hooks = HookRegistry()
    mgr = AgentManager(executor=exec_, max_parallel=4, hooks=hooks)
    register_auto_security(mgr, hooks=hooks)

    code_run = await mgr.spawn(
        AgentSpec(type="code", prompt="ship a parser", files=frozenset({"/x.py"}))
    )
    await mgr.wait(code_run.id)
    for _ in range(20):
        await asyncio.sleep(0.02)
        if any(r.spec.type == "security" for r in mgr.list_runs()):
            break

    sec_runs = [r for r in mgr.list_runs() if r.spec.type == "security"]
    assert len(sec_runs) == 1
    await mgr.wait(sec_runs[0].id)
    assert "code" in seen_types
    assert "security" in seen_types


async def test_failed_code_does_not_spawn_security():
    async def exec_(spec, prompt):
        if spec.type == "code":
            raise RuntimeError("compile error")
        return RunResult()

    hooks = HookRegistry()
    mgr = AgentManager(executor=exec_, max_parallel=4, hooks=hooks)
    register_auto_security(mgr, hooks=hooks)
    code_run = await mgr.spawn(AgentSpec(type="code", prompt="oops"))
    await mgr.wait(code_run.id)
    for _ in range(20):
        await asyncio.sleep(0.02)

    sec_runs = [r for r in mgr.list_runs() if r.spec.type == "security"]
    assert sec_runs == []


async def test_security_completion_does_not_chain():
    """Security agent finishing must not trigger another security agent
    (prevents infinite loops)."""

    async def exec_(spec, prompt):
        return RunResult(output="audit", cost_usd=0.0)

    hooks = HookRegistry()
    mgr = AgentManager(executor=exec_, max_parallel=4, hooks=hooks)
    register_auto_security(mgr, hooks=hooks)
    sec = await mgr.spawn(AgentSpec(type="security", prompt="audit"))
    await mgr.wait(sec.id)
    for _ in range(10):
        await asyncio.sleep(0.02)
    sec_runs = [r for r in mgr.list_runs() if r.spec.type == "security"]
    assert len(sec_runs) == 1


async def test_research_completion_does_not_spawn_security():
    async def exec_(spec, prompt):
        return RunResult(output="found")

    hooks = HookRegistry()
    mgr = AgentManager(executor=exec_, max_parallel=4, hooks=hooks)
    register_auto_security(mgr, hooks=hooks)
    r = await mgr.spawn(AgentSpec(type="research", prompt="look"))
    await mgr.wait(r.id)
    for _ in range(10):
        await asyncio.sleep(0.02)
    sec_runs = [r for r in mgr.list_runs() if r.spec.type == "security"]
    assert sec_runs == []


async def test_security_inherits_files_from_code():
    async def exec_(spec, prompt):
        return RunResult(output="ok", cost_usd=0.0)

    hooks = HookRegistry()
    mgr = AgentManager(executor=exec_, max_parallel=4, hooks=hooks)
    register_auto_security(mgr, hooks=hooks)
    code = await mgr.spawn(
        AgentSpec(type="code", prompt="touch", files=frozenset({"/a.py", "/b.py"}))
    )
    await mgr.wait(code.id)
    for _ in range(20):
        await asyncio.sleep(0.02)
        sec_runs = [r for r in mgr.list_runs() if r.spec.type == "security"]
        if sec_runs:
            break
    sec = sec_runs[0]
    assert sec.spec.files == frozenset({"/a.py", "/b.py"})
    # Auto-spawned reviews use the lower cost cap.
    assert sec.spec.cost_cap_usd < 1.0


async def test_unsubscribe_stops_auto_spawn():
    async def exec_(spec, prompt):
        return RunResult(output="ok")

    hooks = HookRegistry()
    mgr = AgentManager(executor=exec_, max_parallel=4, hooks=hooks)
    unsub = register_auto_security(mgr, hooks=hooks)
    unsub()
    code = await mgr.spawn(AgentSpec(type="code", prompt="x"))
    await mgr.wait(code.id)
    for _ in range(10):
        await asyncio.sleep(0.02)
    sec_runs = [r for r in mgr.list_runs() if r.spec.type == "security"]
    assert sec_runs == []
