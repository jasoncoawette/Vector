from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Awaitable, Callable, Literal

AgentType = Literal["code", "research", "writer", "tester", "security"]

DEFAULT_COST_CAP_USD = 1.0
DEFAULT_TIMEOUT_S = 600
DEFAULT_MAX_ATTEMPTS = 3
LONG_RUN_S = 600


class RunStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    KILLED = "killed"
    NEEDS_CONFIRM = "needs_confirm"


@dataclass(frozen=True)
class AgentSpec:
    type: AgentType
    prompt: str
    files: frozenset[str] = frozenset()
    fallback_prompt: str | None = None
    cost_cap_usd: float = DEFAULT_COST_CAP_USD
    timeout_s: int = DEFAULT_TIMEOUT_S
    # Self-healing. When success_criteria is None, no verifier runs and
    # behavior matches the legacy one-shot-with-fallback path. When set,
    # the manager retries up to max_attempts, feeding the verifier's
    # reason back into the next attempt's prompt.
    success_criteria: str | None = None
    max_attempts: int = DEFAULT_MAX_ATTEMPTS


@dataclass
class RunResult:
    output: str = ""
    cost_usd: float = 0.0
    meta: dict = field(default_factory=dict)


@dataclass
class Run:
    id: str
    spec: AgentSpec
    status: RunStatus = RunStatus.QUEUED
    output: str = ""
    error: str = ""
    cost_usd: float = 0.0
    fallback_used: bool = False
    attempts_used: int = 0
    last_verifier_reason: str | None = None
    queued_at: float = field(default_factory=time.time)
    started_at: float | None = None
    ended_at: float | None = None
    trace_id: str | None = None
    _task: asyncio.Task | None = field(default=None, repr=False)

    @property
    def elapsed_s(self) -> float | None:
        if self.started_at is None:
            return None
        end = self.ended_at or time.time()
        return end - self.started_at

    @property
    def long_running(self) -> bool:
        e = self.elapsed_s
        return e is not None and e > LONG_RUN_S and self.status == RunStatus.RUNNING

    def summary(self) -> dict:
        return {
            "id": self.id,
            "type": self.spec.type,
            "prompt": self.spec.prompt[:200],
            "status": self.status.value,
            "cost_usd": round(self.cost_usd, 4),
            "fallback_used": self.fallback_used,
            "attempts_used": self.attempts_used,
            "max_attempts": self.spec.max_attempts,
            "last_verifier_reason": self.last_verifier_reason,
            "elapsed_s": round(self.elapsed_s or 0.0, 2),
            "long_running": self.long_running,
            "files": sorted(self.spec.files),
            "output": self.output[:4000],
            "error": self.error,
            "trace_id": self.trace_id,
        }


Executor = Callable[[AgentSpec, str], Awaitable[RunResult]]


def make_run_id() -> str:
    return uuid.uuid4().hex[:12]
