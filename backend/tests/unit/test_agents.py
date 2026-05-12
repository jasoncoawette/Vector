from __future__ import annotations

import asyncio

import pytest

from vector.agents import AgentManager, AgentSpec, RunResult, RunStatus


def _spec(prompt: str = "do thing", **kw) -> AgentSpec:
    base = {"type": "code", "prompt": prompt}
    base.update(kw)
    if "files" in base and not isinstance(base["files"], frozenset):
        base["files"] = frozenset(base["files"])
    return AgentSpec(**base)


async def test_spawn_runs_executor_and_completes():
    async def exec_ok(spec, prompt):
        return RunResult(output=f"done: {prompt}", cost_usd=0.10)

    m = AgentManager(executor=exec_ok)
    run = await m.spawn(_spec("hello"))
    await m.wait(run.id)
    assert run.status == RunStatus.DONE
    assert run.output == "done: hello"
    assert 0.09 <= run.cost_usd <= 0.11


async def test_max_parallel_is_enforced():
    in_flight = 0
    peak = 0
    started = asyncio.Event()
    release = asyncio.Event()

    async def exec_slow(spec, prompt):
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        started.set()
        await release.wait()
        in_flight -= 1
        return RunResult(output="ok")

    m = AgentManager(executor=exec_slow, max_parallel=2)
    runs = [await m.spawn(_spec(f"p{i}")) for i in range(5)]
    await started.wait()
    await asyncio.sleep(0.05)
    assert peak <= 2
    release.set()
    for r in runs:
        await m.wait(r.id)
    assert all(r.status == RunStatus.DONE for r in runs)


async def test_file_conflict_serializes():
    order: list[str] = []
    gate_a = asyncio.Event()

    async def exec_(spec, prompt):
        order.append(f"start:{prompt}")
        if prompt == "A":
            await gate_a.wait()
        order.append(f"end:{prompt}")
        return RunResult(output=prompt)

    m = AgentManager(executor=exec_, max_parallel=3)
    a = await m.spawn(_spec("A", files=["/x.py"]))
    b = await m.spawn(_spec("B", files=["/x.py"]))
    await asyncio.sleep(0.05)
    assert order == ["start:A"]
    gate_a.set()
    await m.wait(a.id)
    await m.wait(b.id)
    assert order == ["start:A", "end:A", "start:B", "end:B"]


async def test_cost_cap_marks_needs_confirm():
    async def exec_expensive(spec, prompt):
        return RunResult(output="big", cost_usd=2.5)

    m = AgentManager(executor=exec_expensive)
    run = await m.spawn(_spec("expensive", cost_cap_usd=1.0))
    await m.wait(run.id)
    assert run.status == RunStatus.NEEDS_CONFIRM
    assert "cap" in run.error


async def test_timeout_marks_failed():
    async def exec_slow(spec, prompt):
        await asyncio.sleep(5)
        return RunResult()

    m = AgentManager(executor=exec_slow)
    run = await m.spawn(_spec("slow", timeout_s=1))
    await m.wait(run.id, timeout=3)
    assert run.status == RunStatus.FAILED
    assert "timeout" in run.error


async def test_fallback_runs_once_after_failure():
    calls: list[str] = []

    async def exec_flaky(spec, prompt):
        calls.append(prompt)
        if prompt == "primary":
            raise RuntimeError("oops")
        return RunResult(output="recovered")

    m = AgentManager(executor=exec_flaky)
    run = await m.spawn(_spec("primary", fallback_prompt="backup"))
    await m.wait(run.id)
    assert run.status == RunStatus.DONE
    assert run.fallback_used is True
    assert run.output == "recovered"
    assert calls == ["primary", "backup"]


async def test_no_fallback_means_stays_failed():
    async def exec_bad(spec, prompt):
        raise RuntimeError("nope")

    m = AgentManager(executor=exec_bad)
    run = await m.spawn(_spec("bad"))
    await m.wait(run.id)
    assert run.status == RunStatus.FAILED
    assert run.fallback_used is False


async def test_kill_running_run():
    started = asyncio.Event()

    async def exec_slow(spec, prompt):
        started.set()
        await asyncio.sleep(10)
        return RunResult()

    m = AgentManager(executor=exec_slow)
    run = await m.spawn(_spec("slow"))
    await started.wait()
    assert await m.kill(run.id, reason="off topic") is True
    await asyncio.sleep(0.05)
    assert run.status == RunStatus.KILLED
    assert run.error == "off topic"


async def test_kill_done_run_returns_false():
    async def exec_fast(spec, prompt):
        return RunResult(output="done")

    m = AgentManager(executor=exec_fast)
    run = await m.spawn(_spec("ok"))
    await m.wait(run.id)
    assert await m.kill(run.id) is False


async def test_killed_run_releases_file_lock():
    started = asyncio.Event()

    async def exec_slow(spec, prompt):
        started.set()
        await asyncio.sleep(10)
        return RunResult()

    m = AgentManager(executor=exec_slow)
    a = await m.spawn(_spec("A", files=["/shared.py"]))
    await started.wait()
    await m.kill(a.id)
    b = await m.spawn(_spec("B", files=["/shared.py"]))
    await m.wait(b.id, timeout=2)
    assert b.status != RunStatus.QUEUED


async def test_max_parallel_must_be_positive():
    async def exec_(spec, prompt):
        return RunResult()

    with pytest.raises(ValueError):
        AgentManager(executor=exec_, max_parallel=0)


async def test_summary_redacts_long_output():
    huge = "x" * 10000

    async def exec_big(spec, prompt):
        return RunResult(output=huge)

    m = AgentManager(executor=exec_big)
    run = await m.spawn(_spec("big"))
    await m.wait(run.id)
    s = run.summary()
    assert len(s["output"]) <= 4000
