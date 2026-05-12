"""Pydantic schemas for inbound Plan payloads.

The brain can either return a Plan as a structured JSON reply (parsed
here) or a caller can POST one directly to /plans. Either way we
validate the shape at the boundary; the executor only sees clean Plan
dataclasses from `plans.types`.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from .types import (
    Plan,
    PlanValidationError,
    Step,
    StepAgentType,
    make_plan_id,
    validate,
)


class StepIn(BaseModel):
    id: int = Field(ge=1)
    agent: StepAgentType
    prompt: str = Field(min_length=1, max_length=8000)
    depends_on: list[int] = Field(default_factory=list, max_length=16)
    files: list[str] = Field(default_factory=list, max_length=32)
    success_criteria: str | None = Field(default=None, max_length=2000)
    cost_cap_usd: float = Field(default=1.0, gt=0, le=10.0)
    timeout_s: int = Field(default=600, ge=1, le=3600)
    max_attempts: int = Field(default=3, ge=1, le=5)


class PlanIn(BaseModel):
    goal: str = Field(min_length=1, max_length=2000)
    steps: list[StepIn] = Field(min_length=1, max_length=16)


def build_plan(payload: PlanIn, *, plan_id: str | None = None) -> Plan:
    """Convert a validated PlanIn into the immutable Plan dataclass.

    Raises PlanValidationError on DAG / placeholder violations."""
    steps = tuple(
        Step(
            id=s.id,
            agent=s.agent,
            prompt=s.prompt,
            depends_on=tuple(s.depends_on),
            files=frozenset(s.files),
            success_criteria=s.success_criteria,
            cost_cap_usd=s.cost_cap_usd,
            timeout_s=s.timeout_s,
            max_attempts=s.max_attempts,
        )
        for s in payload.steps
    )
    plan = Plan(id=plan_id or make_plan_id(), goal=payload.goal, steps=steps)
    validate(plan)
    return plan
