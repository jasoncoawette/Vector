from __future__ import annotations

import asyncio
from collections import defaultdict

import pytest

from vector.agents import AgentManager, AgentSpec, RunResult, RunStatus
from vector.plans import Plan, PlanRunner, Step
from vector.plans.types import PlanStatus, StepStatus


def _step(id_: int, **kw) -> Step:
    base = {
        "agent": "research",
        "prompt": f"step {id_}",
        "depends_on": (),
    }
    base.update(kw)
    return Step(id=id_, **base)


def _plan(*steps: Step, goal: str = "test") -> Plan:
    return Plan(id="plan-test", goal=goal, steps=steps)


def _outputs() -> dict[int, str]:
    """Collects what each step's executor saw as its prompt, keyed by
    the step number embedded in the agent prompt."""
    return defaultdict(str)


async def test_linear_plan_runs_in_order():
    order: list[int] = []

    async def exec_(spec, prompt):
        # Pull the step id we encoded in the prompt: "step 1"
        sid = int(prompt.split()[1].split("/")[0])
        order.append(sid)
        return RunResult(output=f"out-{sid}", cost_usd=0.01)

    mgr = AgentManager(executor=exec_, max_parallel=4)
    runner = PlanRunner(manager=mgr)
    plan = _plan(
        _step(1, prompt="step 1"),
        _step(2, prompt="step 2", depends_on=(1,)),
        _step(3, prompt="step 3", depends_on=(2,)),
    )
    run = await runner.execute(plan)

    assert order == [1, 2, 3]
    assert run.status == PlanStatus.DONE
    for sr in run.steps.values():
        assert sr.status == StepStatus.DONE


async def test_diamond_runs_branches_in_parallel():
    """A -> {B, C} -> D should run B and C in parallel after A."""
    peak = 0
    in_flight = 0
    release = asyncio.Event()
    seen = set()

    async def exec_(spec, prompt):
        nonlocal in_flight, peak
        sid = int(prompt.split()[1].split("/")[0])
        in_flight += 1
        peak = max(peak, in_flight)
        seen.add(sid)
        # Pause B and C in flight so we can observe their overlap.
        if sid in (2, 3):
            await release.wait()
        in_flight -= 1
        return RunResult(output=f"out-{sid}", cost_usd=0.0)

    mgr = AgentManager(executor=exec_, max_parallel=4)
    runner = PlanRunner(manager=mgr)
    plan = _plan(
        _step(1, prompt="step 1"),
        _step(2, prompt="step 2", depends_on=(1,)),
        _step(3, prompt="step 3", depends_on=(1,)),
        _step(4, prompt="step 4", depends_on=(2, 3)),
    )

    async def run_and_release():
        # Let B + C get in flight, then release.
        await asyncio.sleep(0.05)
        release.set()

    rl = asyncio.create_task(run_and_release())
    run = await runner.execute(plan)
    await rl

    assert peak >= 2  # B and C overlapped
    assert run.status == PlanStatus.DONE
    assert seen == {1, 2, 3, 4}


async def test_placeholder_substitution_threads_output_into_next_prompt():
    saw: list[str] = []

    async def exec_(spec, prompt):
        saw.append(prompt)
        return RunResult(output="LATTICE_FINDING", cost_usd=0.0)

    mgr = AgentManager(executor=exec_, max_parallel=4)
    runner = PlanRunner(manager=mgr)
    plan = _plan(
        _step(1, prompt="research Lattice"),
        _step(
            2,
            prompt="draft using {{step_1.output}} as input",
            depends_on=(1,),
        ),
    )
    await runner.execute(plan)
    assert saw[0] == "research Lattice"
    assert saw[1] == "draft using LATTICE_FINDING as input"


async def test_failed_step_cascades_skip_downstream():
    """If step 2 fails, step 3 (depends on 2) and step 4 (depends on 3)
    are SKIPPED, not RUN."""
    seen: set[int] = set()

    async def exec_(spec, prompt):
        sid = int(prompt.split()[1].split("/")[0])
        seen.add(sid)
        if sid == 2:
            raise RuntimeError("boom")
        return RunResult(output=f"out-{sid}")

    mgr = AgentManager(executor=exec_, max_parallel=4)
    runner = PlanRunner(manager=mgr)
    plan = _plan(
        _step(1, prompt="step 1"),
        _step(2, prompt="step 2", depends_on=(1,)),
        _step(3, prompt="step 3", depends_on=(2,)),
        _step(4, prompt="step 4", depends_on=(3,)),
    )
    run = await runner.execute(plan)

    assert seen == {1, 2}  # 3 and 4 never invoked
    assert run.steps[1].status == StepStatus.DONE
    assert run.steps[2].status == StepStatus.FAILED
    assert run.steps[3].status == StepStatus.SKIPPED
    assert run.steps[4].status == StepStatus.SKIPPED
    assert run.status == PlanStatus.FAILED


async def test_parallel_failure_does_not_kill_sibling():
    """In A -> {B, C}, B failing should not prevent C from completing
    (they're independent siblings)."""

    async def exec_(spec, prompt):
        sid = int(prompt.split()[1].split("/")[0])
        if sid == 2:
            raise RuntimeError("B fails")
        return RunResult(output=f"out-{sid}")

    mgr = AgentManager(executor=exec_, max_parallel=4)
    runner = PlanRunner(manager=mgr)
    plan = _plan(
        _step(1, prompt="step 1"),
        _step(2, prompt="step 2", depends_on=(1,)),
        _step(3, prompt="step 3", depends_on=(1,)),
    )
    run = await runner.execute(plan)
    assert run.steps[2].status == StepStatus.FAILED
    assert run.steps[3].status == StepStatus.DONE
    assert run.status == PlanStatus.FAILED


async def test_cost_rolls_up_across_steps():
    async def exec_(spec, prompt):
        return RunResult(output="ok", cost_usd=0.05)

    mgr = AgentManager(executor=exec_, max_parallel=4)
    runner = PlanRunner(manager=mgr)
    plan = _plan(_step(1), _step(2, depends_on=(1,)), _step(3, depends_on=(2,)))
    run = await runner.execute(plan)
    assert run.total_cost_usd == pytest.approx(0.15)


async def test_persist_callback_invoked_on_every_state_change():
    snapshots: list[PlanStatus] = []

    def persist(plan_run):
        snapshots.append(plan_run.status)

    async def exec_(spec, prompt):
        return RunResult(output="ok")

    mgr = AgentManager(executor=exec_, max_parallel=4)
    runner = PlanRunner(manager=mgr, persist=persist)
    plan = _plan(_step(1), _step(2, depends_on=(1,)))
    await runner.execute(plan)
    # At least: initial RUNNING and final DONE.
    assert PlanStatus.RUNNING in snapshots
    assert PlanStatus.DONE in snapshots


async def test_persist_failure_does_not_break_plan():
    """A crashing persist callback must not abort the plan run."""

    def persist(plan_run):
        raise RuntimeError("disk full")

    async def exec_(spec, prompt):
        return RunResult(output="ok")

    mgr = AgentManager(executor=exec_, max_parallel=4)
    runner = PlanRunner(manager=mgr, persist=persist)
    plan = _plan(_step(1))
    run = await runner.execute(plan)
    assert run.status == PlanStatus.DONE


async def test_substitution_clamps_huge_upstream_output():
    huge = "x" * 50_000
    saw: list[int] = []

    async def exec_(spec, prompt):
        sid = int(prompt.split()[1].split("/")[0])
        saw.append(sid)
        if sid == 1:
            return RunResult(output=huge)
        # Step 2 receives a substituted output capped at the executor's
        # MAX_SUBSTITUTION_CHARS bound.
        assert "x" * 50_000 not in prompt
        return RunResult(output="ok")

    mgr = AgentManager(executor=exec_, max_parallel=4)
    runner = PlanRunner(manager=mgr)
    plan = _plan(
        _step(1, prompt="step 1"),
        _step(2, prompt="step 2 then {{step_1.output}}", depends_on=(1,)),
    )
    run = await runner.execute(plan)
    assert run.status == PlanStatus.DONE
    assert saw == [1, 2]
