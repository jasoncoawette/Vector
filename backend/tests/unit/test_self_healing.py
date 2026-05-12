from __future__ import annotations

import asyncio

import pytest

from vector.agents import AgentManager, AgentSpec, RunResult, RunStatus
from vector.agents.verifier import FakeVerifier, Verdict


def _spec(**kw) -> AgentSpec:
    base = {
        "type": "code",
        "prompt": "do the thing",
        "success_criteria": "the thing is done",
        "max_attempts": 3,
    }
    base.update(kw)
    return AgentSpec(**base)


async def test_succeeds_on_first_attempt_no_retry():
    attempts: list[str] = []

    async def exec_(spec, prompt):
        attempts.append(prompt)
        return RunResult(output="all done", cost_usd=0.01)

    v = FakeVerifier([Verdict(success=True, reason="ok")])
    mgr = AgentManager(executor=exec_, max_parallel=2, verifier=v)
    run = await mgr.spawn(_spec())
    await mgr.wait(run.id)

    assert run.status == RunStatus.DONE
    assert run.attempts_used == 1
    assert run.last_verifier_reason == "ok"
    assert len(attempts) == 1


async def test_retries_with_feedback_then_succeeds():
    attempts: list[str] = []

    async def exec_(spec, prompt):
        attempts.append(prompt)
        return RunResult(output=f"output for: {prompt[:30]}", cost_usd=0.01)

    v = FakeVerifier(
        [
            Verdict(success=False, reason="missed the API contract"),
            Verdict(success=True, reason="fixed"),
        ]
    )
    # Strip retry backoff to keep the test fast.
    from vector.agents import manager as manager_mod

    original = manager_mod.RETRY_BACKOFF_S
    manager_mod.RETRY_BACKOFF_S = (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    try:
        mgr = AgentManager(executor=exec_, max_parallel=2, verifier=v)
        run = await mgr.spawn(_spec())
        await mgr.wait(run.id)
    finally:
        manager_mod.RETRY_BACKOFF_S = original

    assert run.status == RunStatus.DONE
    assert run.attempts_used == 2
    assert len(attempts) == 2
    # Second attempt should reference the verifier's feedback.
    assert "missed the API contract" in attempts[1]


async def test_gives_up_after_max_attempts():
    async def exec_(spec, prompt):
        return RunResult(output="still wrong", cost_usd=0.01)

    v = FakeVerifier(
        [
            Verdict(success=False, reason="r1"),
            Verdict(success=False, reason="r2"),
            Verdict(success=False, reason="r3"),
        ]
    )
    from vector.agents import manager as manager_mod

    original = manager_mod.RETRY_BACKOFF_S
    manager_mod.RETRY_BACKOFF_S = (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    try:
        mgr = AgentManager(executor=exec_, max_parallel=2, verifier=v)
        run = await mgr.spawn(_spec(max_attempts=3))
        await mgr.wait(run.id)
    finally:
        manager_mod.RETRY_BACKOFF_S = original

    assert run.status == RunStatus.FAILED
    assert run.attempts_used == 3
    assert "r3" in run.error
    assert run.last_verifier_reason == "r3"


async def test_executor_failure_counts_as_attempt_and_retries():
    """If the executor itself errors (not a verifier rejection), the
    retry loop still uses the next attempt with the error as feedback."""
    seq: list[str] = []

    async def exec_(spec, prompt):
        seq.append(prompt)
        if len(seq) == 1:
            raise RuntimeError("first crash")
        return RunResult(output="recovered", cost_usd=0.01)

    v = FakeVerifier([Verdict(success=True, reason="ok")])
    from vector.agents import manager as manager_mod

    original = manager_mod.RETRY_BACKOFF_S
    manager_mod.RETRY_BACKOFF_S = (0.0,) * 6
    try:
        mgr = AgentManager(executor=exec_, max_parallel=2, verifier=v)
        run = await mgr.spawn(_spec())
        await mgr.wait(run.id)
    finally:
        manager_mod.RETRY_BACKOFF_S = original

    assert run.status == RunStatus.DONE
    assert run.attempts_used == 2
    assert "first crash" in seq[1]  # feedback from the prior error


async def test_cost_cap_breach_is_sticky_no_retry():
    """If a single attempt blows the cost cap, the run goes
    NEEDS_CONFIRM and the loop does not keep trying."""

    async def exec_(spec, prompt):
        return RunResult(output="big", cost_usd=2.0)

    v = FakeVerifier([Verdict(success=True, reason="ok")])
    mgr = AgentManager(executor=exec_, max_parallel=2, verifier=v)
    run = await mgr.spawn(_spec(cost_cap_usd=1.0))
    await mgr.wait(run.id)

    assert run.status == RunStatus.NEEDS_CONFIRM
    assert run.attempts_used == 1
    assert "cap" in run.error


async def test_no_verifier_falls_back_to_legacy_path():
    """When the manager has no verifier (or the spec has no criteria),
    behavior matches the prior one-shot-with-fallback flow."""
    attempts: list[str] = []

    async def exec_(spec, prompt):
        attempts.append(prompt)
        if prompt == "primary":
            raise RuntimeError("nope")
        return RunResult(output="ok", cost_usd=0.0)

    mgr = AgentManager(executor=exec_, max_parallel=2, verifier=None)
    run = await mgr.spawn(
        AgentSpec(
            type="research", prompt="primary", fallback_prompt="backup"
        )
    )
    await mgr.wait(run.id)
    assert run.status == RunStatus.DONE
    assert run.fallback_used is True
    assert run.attempts_used == 2


async def test_no_criteria_skips_verifier():
    """Even with a verifier wired, a spec without success_criteria runs
    the legacy path (no verifier call)."""
    v_calls = 0

    class CountingVerifier:
        async def check(self, criteria, output):
            nonlocal v_calls
            v_calls += 1
            return Verdict(success=True, reason="ok")

    async def exec_(spec, prompt):
        return RunResult(output="ok", cost_usd=0.0)

    mgr = AgentManager(executor=exec_, max_parallel=2, verifier=CountingVerifier())
    run = await mgr.spawn(AgentSpec(type="research", prompt="no criteria"))
    await mgr.wait(run.id)
    assert run.status == RunStatus.DONE
    assert v_calls == 0


async def test_verifier_crash_treated_as_pass_with_warning():
    """A broken verifier mustn't deadlock the agent. We accept the
    output and stamp last_verifier_reason with the crash."""

    class CrashingVerifier:
        async def check(self, criteria, output):
            raise RuntimeError("verifier offline")

    async def exec_(spec, prompt):
        return RunResult(output="ok", cost_usd=0.01)

    mgr = AgentManager(executor=exec_, max_parallel=2, verifier=CrashingVerifier())
    run = await mgr.spawn(_spec())
    await mgr.wait(run.id)
    assert run.status == RunStatus.DONE
    assert "verifier crashed" in (run.last_verifier_reason or "")


async def test_verifier_cost_added_to_run():
    """Verifier cost rolls into the run's cost_usd."""

    async def exec_(spec, prompt):
        return RunResult(output="ok", cost_usd=0.10)

    v = FakeVerifier([Verdict(success=True, reason="ok", cost_usd=0.002)])
    mgr = AgentManager(executor=exec_, max_parallel=2, verifier=v)
    run = await mgr.spawn(_spec())
    await mgr.wait(run.id)
    assert run.cost_usd == pytest.approx(0.102)
