"""Plan + Step: the DAG primitive borrowed from JARVIS.

A `Plan` is a list of `Step`s. Each step names an agent type, carries a
prompt, and declares its dependencies on other steps' outputs. Steps
with no remaining unfulfilled deps are leaves; the executor runs leaves
in parallel, replaces placeholder references in the prompt with the
upstream step's output, and continues until every step is done or one
fails terminally.

Placeholder syntax: `{{step_N.output}}` (where N is a 1-based step id).
The executor substitutes before sending the prompt to the sub-agent.
"""
from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Literal


# Re-use the agent literal so the brain can plan any sub-agent type.
StepAgentType = Literal["code", "research", "writer", "tester", "security"]


PLACEHOLDER_RE = re.compile(r"\{\{\s*step_(\d+)\.output\s*\}\}")


class StepStatus(str, Enum):
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"  # upstream failed; we skip rather than try


class PlanStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    PARTIAL = "partial"  # at least one step skipped


@dataclass(frozen=True)
class Step:
    id: int
    agent: StepAgentType
    prompt: str
    depends_on: tuple[int, ...] = ()
    files: frozenset[str] = frozenset()
    success_criteria: str | None = None
    cost_cap_usd: float = 1.0
    timeout_s: int = 600
    max_attempts: int = 3


@dataclass
class StepRun:
    step_id: int
    status: StepStatus = StepStatus.PENDING
    output: str = ""
    error: str = ""
    cost_usd: float = 0.0
    run_id: str | None = None  # agent run id once it spawns
    started_at: float | None = None
    ended_at: float | None = None

    def to_dict(self) -> dict:
        return {
            "step_id": self.step_id,
            "status": self.status.value,
            "output": self.output[:4000],
            "error": self.error,
            "cost_usd": round(self.cost_usd, 4),
            "run_id": self.run_id,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
        }


@dataclass(frozen=True)
class Plan:
    id: str
    goal: str
    steps: tuple[Step, ...]
    created_at: float = field(default_factory=time.time)

    def step(self, step_id: int) -> Step | None:
        for s in self.steps:
            if s.id == step_id:
                return s
        return None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "goal": self.goal,
            "created_at": self.created_at,
            "steps": [
                {
                    "id": s.id,
                    "agent": s.agent,
                    "prompt": s.prompt,
                    "depends_on": list(s.depends_on),
                    "files": sorted(s.files),
                    "success_criteria": s.success_criteria,
                    "cost_cap_usd": s.cost_cap_usd,
                    "timeout_s": s.timeout_s,
                    "max_attempts": s.max_attempts,
                }
                for s in self.steps
            ],
        }


@dataclass
class PlanRun:
    plan: Plan
    status: PlanStatus = PlanStatus.PENDING
    steps: dict[int, StepRun] = field(default_factory=dict)
    started_at: float | None = None
    ended_at: float | None = None
    error: str = ""

    def __post_init__(self) -> None:
        if not self.steps:
            self.steps = {s.id: StepRun(step_id=s.id) for s in self.plan.steps}

    @property
    def total_cost_usd(self) -> float:
        return sum(sr.cost_usd for sr in self.steps.values())

    def to_dict(self) -> dict:
        return {
            "plan": self.plan.to_dict(),
            "status": self.status.value,
            "steps": [self.steps[s.id].to_dict() for s in self.plan.steps],
            "total_cost_usd": round(self.total_cost_usd, 4),
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "error": self.error,
        }


# ---------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------


class PlanValidationError(ValueError):
    pass


def validate(plan: Plan) -> None:
    """Reject malformed plans before they reach the executor.

    Rules:
      - step ids must be unique and start at 1
      - depends_on must reference real ids and never itself
      - the dependency graph must be a DAG (no cycles)
      - placeholders {{step_N.output}} must reference an id in depends_on
    """
    if not plan.steps:
        raise PlanValidationError("plan must have at least one step")

    ids = [s.id for s in plan.steps]
    if len(set(ids)) != len(ids):
        raise PlanValidationError("step ids must be unique")

    id_set = set(ids)
    for s in plan.steps:
        for dep in s.depends_on:
            if dep == s.id:
                raise PlanValidationError(f"step {s.id} depends on itself")
            if dep not in id_set:
                raise PlanValidationError(
                    f"step {s.id} depends on unknown step {dep}"
                )

    if _has_cycle(plan):
        raise PlanValidationError("plan dependency graph has a cycle")

    for s in plan.steps:
        for match in PLACEHOLDER_RE.finditer(s.prompt):
            referenced = int(match.group(1))
            if referenced not in s.depends_on:
                raise PlanValidationError(
                    f"step {s.id} references step_{referenced} but does not "
                    f"declare it in depends_on"
                )


def _has_cycle(plan: Plan) -> bool:
    """Iterative DFS over the depends_on adjacency to detect cycles."""
    color: dict[int, int] = {s.id: 0 for s in plan.steps}  # 0=white, 1=gray, 2=black
    deps: dict[int, tuple[int, ...]] = {s.id: s.depends_on for s in plan.steps}

    def dfs(start: int) -> bool:
        stack: list[tuple[int, int]] = [(start, 0)]
        while stack:
            node, idx = stack[-1]
            if idx == 0:
                if color[node] == 1:
                    return True
                if color[node] == 2:
                    stack.pop()
                    continue
                color[node] = 1
            children = deps[node]
            if idx < len(children):
                stack[-1] = (node, idx + 1)
                child = children[idx]
                if color[child] == 1:
                    return True
                if color[child] == 0:
                    stack.append((child, 0))
            else:
                color[node] = 2
                stack.pop()
        return False

    for s in plan.steps:
        if color[s.id] == 0 and dfs(s.id):
            return True
    return False


def make_plan_id() -> str:
    return "plan-" + uuid.uuid4().hex[:10]
