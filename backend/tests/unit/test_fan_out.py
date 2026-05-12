from __future__ import annotations

import asyncio

import pytest

from vector.agents import AgentManager, AgentSpec, RunResult, RunStatus
from vector.agents.executor import SYSTEM_PROMPTS


@pytest.fixture()
def specs() -> list[AgentSpec]:
    return [
        AgentSpec(type="code", prompt="ship it"),
        AgentSpec(type="tester", prompt="cover the public surface"),
        AgentSpec(type="security", prompt="audit the diff"),
        AgentSpec(type="research", prompt="find the spec"),
    ]


async def test_new_types_have_system_prompts():
    assert "tester" in SYSTEM_PROMPTS
    assert "security" in SYSTEM_PROMPTS


async def test_fan_out_spawns_all(specs):
    seen: list[str] = []

    async def exec_(spec, prompt):
        seen.append(spec.type)
        return RunResult(output=f"{spec.type} done", cost_usd=0.01)

    mgr = AgentManager(executor=exec_, max_parallel=4)
    runs = await mgr.fan_out(specs)
    assert len(runs) == 4
    for r in runs:
        await mgr.wait(r.id)
    assert sorted(seen) == ["code", "research", "security", "tester"]


async def test_fan_out_respects_parallel_cap(specs):
    peak = 0
    in_flight = 0
    release = asyncio.Event()
    started = asyncio.Event()

    async def exec_(spec, prompt):
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        started.set()
        await release.wait()
        in_flight -= 1
        return RunResult(output="ok")

    mgr = AgentManager(executor=exec_, max_parallel=2)
    runs = await mgr.fan_out(specs)
    await started.wait()
    await asyncio.sleep(0.02)
    assert peak <= 2
    release.set()
    for r in runs:
        await mgr.wait(r.id)


async def test_security_run_is_first_class(specs):
    async def exec_(spec, prompt):
        return RunResult(output=f"{spec.type} audit", cost_usd=0.0)

    mgr = AgentManager(executor=exec_, max_parallel=4)
    sec = [s for s in specs if s.type == "security"][0]
    run = await mgr.spawn(sec)
    await mgr.wait(run.id)
    assert run.status == RunStatus.DONE
    assert "audit" in run.output
