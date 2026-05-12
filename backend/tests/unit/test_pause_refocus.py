from __future__ import annotations

import asyncio

import pytest

from vector.agents import AgentManager, AgentSpec, RunResult, RunStatus


async def test_pause_holds_new_starts():
    started: list[str] = []

    async def exec_(spec, prompt):
        started.append(prompt)
        return RunResult(output="ok")

    mgr = AgentManager(executor=exec_, max_parallel=2)
    await mgr.pause()
    run = await mgr.spawn(AgentSpec(type="research", prompt="held"))
    await asyncio.sleep(0.05)
    assert started == []
    assert run.status == RunStatus.QUEUED

    await mgr.resume()
    await mgr.wait(run.id)
    assert started == ["held"]
    assert run.status == RunStatus.DONE


async def test_pause_lets_inflight_finish():
    release = asyncio.Event()
    finished: list[str] = []

    async def exec_(spec, prompt):
        await release.wait()
        finished.append(prompt)
        return RunResult(output="done")

    mgr = AgentManager(executor=exec_, max_parallel=2)
    in_flight = await mgr.spawn(AgentSpec(type="research", prompt="alpha"))
    await asyncio.sleep(0.02)
    await mgr.pause()
    held = await mgr.spawn(AgentSpec(type="research", prompt="beta"))
    release.set()
    await mgr.wait(in_flight.id)
    assert in_flight.status == RunStatus.DONE
    assert finished == ["alpha"]
    assert held.status == RunStatus.QUEUED
    await mgr.resume()
    await mgr.wait(held.id)
    assert held.status == RunStatus.DONE


async def test_refocus_kills_and_respawns():
    started = asyncio.Event()
    captured: list[str] = []

    async def exec_(spec, prompt):
        captured.append(prompt)
        if prompt == "v1":
            started.set()
            await asyncio.sleep(5)
        return RunResult(output=f"ok {prompt}")

    mgr = AgentManager(executor=exec_, max_parallel=2)
    original = await mgr.spawn(AgentSpec(type="code", prompt="v1", files=frozenset({"/x.py"})))
    await started.wait()
    new_run = await mgr.refocus(original.id, "v2 — tighter")
    assert new_run is not None
    await mgr.wait(new_run.id)
    assert original.status == RunStatus.KILLED
    assert original.error == "refocused"
    assert new_run.status == RunStatus.DONE
    assert "v2" in captured[-1]


async def test_refocus_unknown_returns_none():
    async def exec_(spec, prompt):
        return RunResult()

    mgr = AgentManager(executor=exec_, max_parallel=2)
    assert await mgr.refocus("nope", "x") is None


async def test_refocus_preserves_file_lock():
    started = asyncio.Event()

    async def exec_(spec, prompt):
        started.set()
        await asyncio.sleep(0.1)
        return RunResult(output=prompt)

    mgr = AgentManager(executor=exec_, max_parallel=2)
    a = await mgr.spawn(AgentSpec(type="code", prompt="orig", files=frozenset({"/y.py"})))
    await started.wait()
    new = await mgr.refocus(a.id, "tighter")
    assert new is not None
    assert new.spec.files == frozenset({"/y.py"})
    await mgr.wait(new.id)


async def test_paused_property_reflects_state():
    async def exec_(spec, prompt):
        return RunResult()

    mgr = AgentManager(executor=exec_, max_parallel=2)
    assert mgr.paused is False
    await mgr.pause()
    assert mgr.paused is True
    await mgr.resume()
    assert mgr.paused is False
