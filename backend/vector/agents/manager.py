from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

from ..hooks import HookRegistry, get_hooks
from .types import (
    AgentSpec,
    Executor,
    Run,
    RunResult,
    RunStatus,
    make_run_id,
)


class OverCostCap(Exception):
    """Executor signals it would exceed the per-run cost cap."""


@dataclass
class _Reservation:
    run_id: str
    files: frozenset[str]


class AgentManager:
    """Owns the run queue, the parallel cap, and the file-conflict guard.

    `executor` is injected so tests don't call out to Claude.
    """

    def __init__(
        self,
        executor: Executor,
        *,
        max_parallel: int = 3,
        hooks: HookRegistry | None = None,
    ) -> None:
        if max_parallel < 1:
            raise ValueError("max_parallel must be >= 1")
        self._executor = executor
        self._max_parallel = max_parallel
        self._hooks = hooks or get_hooks()
        self._runs: dict[str, Run] = {}
        self._busy_files: set[str] = set()
        self._lock = asyncio.Lock()
        self._slot = asyncio.Condition()
        self._running = 0
        self._paused = False

    def list_runs(self) -> list[Run]:
        return list(self._runs.values())

    def get(self, run_id: str) -> Run | None:
        return self._runs.get(run_id)

    async def spawn(self, spec: AgentSpec) -> Run:
        run = Run(id=make_run_id(), spec=spec)
        self._runs[run.id] = run
        run._task = asyncio.create_task(self._drive(run))
        return run

    async def fan_out(self, specs: list[AgentSpec]) -> list[Run]:
        """Spawn many specs in one call. The manager's parallel cap +
        file-conflict guard still apply — fan_out only saves the caller
        from a loop and guarantees the runs appear in deterministic order."""
        runs: list[Run] = []
        for spec in specs:
            runs.append(await self.spawn(spec))
        return runs

    async def kill(self, run_id: str, *, reason: str = "killed by user") -> bool:
        run = self._runs.get(run_id)
        if run is None or run.status in (
            RunStatus.DONE,
            RunStatus.FAILED,
            RunStatus.KILLED,
        ):
            return False
        if run._task is not None:
            run._task.cancel()
        run.status = RunStatus.KILLED
        run.error = reason
        run.ended_at = time.time()
        await self._release_files(run.spec.files)
        return True

    async def wait(self, run_id: str, *, timeout: float | None = None) -> Run:
        run = self._runs[run_id]
        if run._task is not None:
            try:
                await asyncio.wait_for(asyncio.shield(run._task), timeout=timeout)
            except asyncio.CancelledError:
                pass
            except asyncio.TimeoutError:
                pass
        return run

    async def _drive(self, run: Run) -> None:
        try:
            await self._acquire_slot(run)
            try:
                await self._run_once(run, run.spec.prompt, fallback=False)
                if run.status == RunStatus.FAILED and run.spec.fallback_prompt:
                    run.fallback_used = True
                    run.status = RunStatus.RUNNING
                    run.error = ""
                    await self._run_once(run, run.spec.fallback_prompt, fallback=True)
            finally:
                await self._release_files(run.spec.files)
                async with self._slot:
                    self._running -= 1
                    self._slot.notify_all()
                await self._hooks.emit("agent_complete", {"run": run.summary()})
        except asyncio.CancelledError:
            run.status = RunStatus.KILLED
            run.ended_at = run.ended_at or time.time()
            await self._hooks.emit("agent_complete", {"run": run.summary()})

    async def _acquire_slot(self, run: Run) -> None:
        async with self._slot:
            while (
                self._paused
                or self._running >= self._max_parallel
                or self._files_busy(run.spec.files)
            ):
                await self._slot.wait()
            self._running += 1
            self._busy_files.update(run.spec.files)

    async def pause(self) -> None:
        """Hold new starts. In-flight runs are allowed to complete."""
        async with self._slot:
            self._paused = True

    async def resume(self) -> None:
        async with self._slot:
            self._paused = False
            self._slot.notify_all()

    @property
    def paused(self) -> bool:
        return self._paused

    async def refocus(self, run_id: str, new_prompt: str) -> Run | None:
        """Kill an in-flight run and respawn with a tighter scope.

        Returns the new Run, or None if the original run is unknown.
        File-set, fallback, cost_cap, timeout are preserved.
        """
        old = self._runs.get(run_id)
        if old is None:
            return None
        await self.kill(run_id, reason="refocused")
        from .types import AgentSpec

        new_spec = AgentSpec(
            type=old.spec.type,
            prompt=new_prompt,
            files=old.spec.files,
            fallback_prompt=old.spec.fallback_prompt,
            cost_cap_usd=old.spec.cost_cap_usd,
            timeout_s=old.spec.timeout_s,
        )
        return await self.spawn(new_spec)

    def _files_busy(self, files: frozenset[str]) -> bool:
        return any(f in self._busy_files for f in files)

    async def _release_files(self, files: frozenset[str]) -> None:
        async with self._slot:
            for f in files:
                self._busy_files.discard(f)
            self._slot.notify_all()

    async def _run_once(self, run: Run, prompt: str, *, fallback: bool) -> None:
        run.status = RunStatus.RUNNING
        if run.started_at is None:
            run.started_at = time.time()
        try:
            result: RunResult = await asyncio.wait_for(
                self._executor(run.spec, prompt),
                timeout=run.spec.timeout_s,
            )
            new_cost = run.cost_usd + result.cost_usd
            if new_cost > run.spec.cost_cap_usd:
                run.cost_usd = new_cost
                run.status = RunStatus.NEEDS_CONFIRM
                run.error = f"cost {new_cost:.2f} exceeded cap {run.spec.cost_cap_usd:.2f}"
                run.ended_at = time.time()
                return
            run.cost_usd = new_cost
            run.output = result.output
            run.status = RunStatus.DONE
            run.ended_at = time.time()
        except asyncio.TimeoutError:
            run.status = RunStatus.FAILED
            run.error = f"timeout after {run.spec.timeout_s}s"
            run.ended_at = time.time()
        except OverCostCap as e:
            run.status = RunStatus.NEEDS_CONFIRM
            run.error = str(e)
            run.ended_at = time.time()
        except Exception as e:
            run.status = RunStatus.FAILED
            run.error = f"{type(e).__name__}: {e}"
            run.ended_at = time.time()
