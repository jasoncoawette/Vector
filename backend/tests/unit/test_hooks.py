from __future__ import annotations

import asyncio

import pytest

from vector.hooks import HookRegistry


async def test_async_listener_called():
    reg = HookRegistry()
    seen: list[dict] = []

    async def listener(payload: dict) -> None:
        seen.append(payload)

    reg.on("agent_complete", listener)
    await reg.emit("agent_complete", {"id": "a"})
    assert seen == [{"id": "a"}]


async def test_sync_listener_called():
    reg = HookRegistry()
    seen: list[dict] = []
    reg.on("tool_call_complete", lambda p: seen.append(p))
    await reg.emit("tool_call_complete", {"tool": "x"})
    assert seen == [{"tool": "x"}]


async def test_listener_exception_does_not_break_emit():
    reg = HookRegistry()
    seen: list[str] = []

    async def bad(_p):
        raise RuntimeError("boom")

    async def good(_p):
        seen.append("ok")

    reg.on("agent_complete", bad)
    reg.on("agent_complete", good)
    await reg.emit("agent_complete", {})
    assert seen == ["ok"]


def test_unsubscribe_stops_calls():
    reg = HookRegistry()
    calls = []
    unsub = reg.on("agent_complete", lambda p: calls.append(p))
    assert reg.listener_count("agent_complete") == 1
    unsub()
    assert reg.listener_count("agent_complete") == 0


async def test_emit_nowait_schedules_async_listener():
    reg = HookRegistry()
    seen: list[dict] = []

    async def listener(payload):
        seen.append(payload)

    reg.on("agent_complete", listener)
    reg.emit_nowait("agent_complete", {"x": 1})
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert seen == [{"x": 1}]


async def test_audit_emits_tool_call_complete():
    from vector import audit
    from vector.hooks import set_hooks

    reg = HookRegistry()
    seen: list[dict] = []
    reg.on("tool_call_complete", lambda p: seen.append(p))
    set_hooks(reg)
    try:
        audit.record("file.read", "brain", {"path": "/x"}, {"ok": True}, ok=True)
        await asyncio.sleep(0)
        assert seen and seen[0]["tool"] == "file.read"
    finally:
        set_hooks(None)


async def test_agent_manager_emits_agent_complete():
    from vector.agents import AgentManager, AgentSpec, RunResult
    from vector.hooks import HookRegistry as HR

    reg = HR()
    seen: list[dict] = []

    async def listener(payload):
        seen.append(payload)

    reg.on("agent_complete", listener)

    async def exec_fast(spec, prompt):
        return RunResult(output="ok", cost_usd=0.01)

    mgr = AgentManager(executor=exec_fast, max_parallel=2, hooks=reg)
    run = await mgr.spawn(AgentSpec(type="research", prompt="go"))
    await mgr.wait(run.id)
    await asyncio.sleep(0)
    assert seen and seen[0]["run"]["status"] == "done"
