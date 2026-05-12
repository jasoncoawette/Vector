"""Plan executor.

Walks the DAG wave-by-wave:
  1. Find all steps whose deps are DONE and which are still PENDING.
  2. Substitute `{{step_N.output}}` placeholders into each ready step's
     prompt with the upstream step's output.
  3. Spawn them as AgentRuns via the AgentManager (so the existing
     parallel cap, file-lock guard, verifier retry, and cost cap all
     apply per-step automatically).
  4. Await the wave. If any step failed, mark all transitive downstream
     steps as SKIPPED and continue draining whatever's still ready.
  5. Repeat until no step is ready and none are running.

We do NOT reimplement parallel scheduling — that lives in AgentManager.
The Plan executor's only job is DAG traversal + placeholder rewriting.
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Awaitable, Callable

from ..agents import AgentManager
from ..agents.types import AgentSpec, RunStatus
from ..hooks import HookRegistry, get_hooks
from ..store import events as events_store
from ..tracing import current_trace_id, new_trace_id, trace
from .types import (
    PLACEHOLDER_RE,
    Plan,
    PlanRun,
    PlanStatus,
    Step,
    StepRun,
    StepStatus,
    validate,
)

logger = logging.getLogger("vector.plans.executor")

# How much of an upstream step's output to substitute into a downstream
# prompt. Caps prompt bloat when one step produces a megabyte of text.
MAX_SUBSTITUTION_CHARS = 4000


PersistFn = Callable[[PlanRun], Awaitable[None] | None]


class PlanRunner:
    """In-memory plan registry plus the DAG-walking executor.

    `persist` is an optional callback invoked at every state change so
    the FastAPI layer can write through to SQLite (and tests can inject
    a no-op)."""

    def __init__(
        self,
        manager: AgentManager,
        *,
        hooks: HookRegistry | None = None,
        persist: PersistFn | None = None,
    ) -> None:
        self._manager = manager
        self._hooks = hooks or get_hooks()
        self._persist = persist
        self._runs: dict[str, PlanRun] = {}

    def get(self, plan_id: str) -> PlanRun | None:
        return self._runs.get(plan_id)

    def list_runs(self) -> list[PlanRun]:
        return list(self._runs.values())

    def submit(self, plan: Plan) -> tuple[PlanRun, "Awaitable[None]"]:
        """Validate + register the plan synchronously. Returns the
        in-memory PlanRun AND the coroutine that runs it.

        The caller is responsible for scheduling the coroutine (typically
        via FastAPI's BackgroundTasks). We don't asyncio.create_task() it
        here because if `submit()` is called from inside a FastAPI route
        handler, the request's anyio task group will cancel any child
        task as soon as the handler returns the response — killing the
        plan before its first wave completes.

        Tests can `asyncio.create_task(coro)` from outside any TaskGroup
        and the plan runs fine; that's what `execute()` does."""
        plan_run = self._register(plan)
        return plan_run, self._run(plan_run)

    async def execute(self, plan: Plan) -> PlanRun:
        """Run a plan to completion. Returns the final PlanRun."""
        plan_run = self._register(plan)
        await self._run(plan_run)
        return plan_run

    def _register(self, plan: Plan) -> PlanRun:
        """Synchronous setup: validate, register, return. Splitting this
        out of `execute()` is what makes `submit()` safe for
        fire-and-forget — the run lands in `self._runs` before the
        function returns so a subsequent `get()` can never miss it."""
        validate(plan)
        tid = current_trace_id() or new_trace_id()
        plan_run = PlanRun(
            plan=plan, status=PlanStatus.RUNNING, started_at=time.time()
        )
        plan_run._trace_id = tid  # type: ignore[attr-defined]
        self._runs[plan.id] = plan_run
        return plan_run

    async def _run(self, plan_run: PlanRun) -> None:
        tid = getattr(plan_run, "_trace_id", None)
        with trace(tid):
            await self._emit_event("plan_start", plan_run)
            await self._save(plan_run)
            try:
                await self._drive(plan_run)
            except Exception as e:  # noqa: BLE001
                plan_run.status = PlanStatus.FAILED
                plan_run.error = f"{type(e).__name__}: {e}"
                logger.exception("plan execution crashed: %s", plan_run.plan.id)
            finally:
                plan_run.ended_at = time.time()
                if plan_run.status not in (
                    PlanStatus.DONE,
                    PlanStatus.FAILED,
                    PlanStatus.PARTIAL,
                ):
                    plan_run.status = self._final_status(plan_run)
                await self._save(plan_run)
                await self._emit_event("plan_end", plan_run)

    # --- internals ----------------------------------------------------

    async def _drive(self, plan_run: PlanRun) -> None:
        while True:
            ready = [s for s in plan_run.plan.steps if self._is_ready(s, plan_run)]
            if not ready:
                # No leaves; either everything's terminal or we have a stuck
                # graph (shouldn't happen — validate() rules cycles out).
                break

            # Mark ready, then spawn all and gather. AgentManager enforces
            # the global parallel cap; this gather is bounded by max_parallel
            # in practice.
            await asyncio.gather(
                *(self._run_step(plan_run, step) for step in ready)
            )

    def _is_ready(self, step: Step, plan_run: PlanRun) -> bool:
        sr = plan_run.steps[step.id]
        if sr.status != StepStatus.PENDING:
            return False
        for dep in step.depends_on:
            dep_run = plan_run.steps.get(dep)
            if dep_run is None:
                # Validation should have caught this; defensive in case.
                return False
            if dep_run.status in (StepStatus.FAILED, StepStatus.SKIPPED):
                # Cascade: this step can never satisfy its deps.
                self._cascade_skip(plan_run, step.id, reason=f"upstream step_{dep} {dep_run.status.value}")
                return False
            if dep_run.status != StepStatus.DONE:
                return False
        return True

    def _cascade_skip(self, plan_run: PlanRun, root_id: int, *, reason: str) -> None:
        """Mark root_id and every step transitively dependent on it as SKIPPED."""
        # BFS over the reverse-dep graph starting at root_id.
        impacted: set[int] = {root_id}
        added = True
        while added:
            added = False
            for s in plan_run.plan.steps:
                if s.id in impacted:
                    continue
                if any(dep in impacted for dep in s.depends_on):
                    impacted.add(s.id)
                    added = True
        for sid in impacted:
            sr = plan_run.steps[sid]
            if sr.status in (StepStatus.PENDING, StepStatus.READY):
                sr.status = StepStatus.SKIPPED
                sr.error = reason
                sr.ended_at = time.time()

    async def _run_step(self, plan_run: PlanRun, step: Step) -> None:
        sr = plan_run.steps[step.id]
        sr.status = StepStatus.RUNNING
        sr.started_at = time.time()
        await self._emit_event(
            "plan_step_start",
            plan_run,
            meta={"step_id": step.id, "agent": step.agent},
        )

        try:
            prompt = self._substitute(step.prompt, plan_run)
            spec = AgentSpec(
                type=step.agent,
                prompt=prompt,
                files=step.files,
                cost_cap_usd=step.cost_cap_usd,
                timeout_s=step.timeout_s,
                success_criteria=step.success_criteria,
                max_attempts=step.max_attempts,
            )
            agent_run = await self._manager.spawn(spec)
            sr.run_id = agent_run.id
            await self._manager.wait(agent_run.id)
            sr.cost_usd = agent_run.cost_usd
            if agent_run.status == RunStatus.DONE:
                sr.status = StepStatus.DONE
                sr.output = agent_run.output
            else:
                sr.status = StepStatus.FAILED
                sr.error = agent_run.error or agent_run.status.value
                self._cascade_skip(plan_run, step.id, reason=f"step_{step.id} failed")
        except Exception as e:  # noqa: BLE001
            sr.status = StepStatus.FAILED
            sr.error = f"{type(e).__name__}: {e}"
            self._cascade_skip(plan_run, step.id, reason=f"step_{step.id} crashed")
        finally:
            sr.ended_at = time.time()
            await self._emit_event(
                "plan_step_end",
                plan_run,
                meta={
                    "step_id": step.id,
                    "status": sr.status.value,
                    "cost_usd": sr.cost_usd,
                },
            )
            await self._save(plan_run)

    def _substitute(self, prompt: str, plan_run: PlanRun) -> str:
        def replace(match: "re.Match[str]") -> str:
            step_id = int(match.group(1))
            sr = plan_run.steps.get(step_id)
            if sr is None or sr.status != StepStatus.DONE:
                # Should not happen — validate() + _is_ready() guarantee
                # upstream is DONE before we substitute. Leave the
                # placeholder in place so the failure is visible if it does.
                return match.group(0)
            return sr.output[:MAX_SUBSTITUTION_CHARS]

        return PLACEHOLDER_RE.sub(replace, prompt)

    def _final_status(self, plan_run: PlanRun) -> PlanStatus:
        statuses = {sr.status for sr in plan_run.steps.values()}
        if StepStatus.FAILED in statuses:
            return PlanStatus.FAILED
        if StepStatus.SKIPPED in statuses:
            return PlanStatus.PARTIAL
        if statuses == {StepStatus.DONE}:
            return PlanStatus.DONE
        # Mix of PENDING/READY/RUNNING means we exited the loop unexpectedly.
        return PlanStatus.FAILED

    async def _emit_event(
        self, kind: str, plan_run: PlanRun, *, meta: dict | None = None
    ) -> None:
        """Best-effort event emission; never blocks the plan."""
        try:
            payload = dict(meta or {})
            payload["plan_id"] = plan_run.plan.id
            payload["plan_status"] = plan_run.status.value
            # Emit via the SQLite events sink if the hooks registry's
            # caller wired one — we route through the same singleton.
            from ..deps import get_db

            events_store.emit(get_db(), kind, meta=payload)
        except Exception:  # noqa: BLE001
            # Telemetry must never break execution.
            pass

    async def _save(self, plan_run: PlanRun) -> None:
        if self._persist is None:
            return
        try:
            result = self._persist(plan_run)
            if hasattr(result, "__await__"):
                await result  # type: ignore[func-returns-value]
        except Exception as e:  # noqa: BLE001
            logger.warning("plan persist failed: %s", e)
