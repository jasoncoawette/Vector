"""Tests for the orchestrator's spawn / fan_out / plans.submit tools.

The orchestrator profile already declares these three tool names in its
allowlist, but until RES-38 the ToolRegistry never registered them, so
the intersection (profile.tools ∩ registry.names()) was empty and the
orchestrator couldn't actually delegate. These tests pin:

  1. Each tool builds the right AgentSpec / Plan and hands it to the
     injected manager / runner.
  2. Profile aliases ('code' → 'developer') resolve through the profile
     registry before the spec is built.
  3. Unknown profile names raise ToolDenied (not a silent passthrough).
  4. Schemas render as well-formed Anthropic tool definitions.
  5. The dynamic-profile audit gate still refuses all three names so
     prompt_engineer can't grant them to itself.
  6. With manager + plans_runner wired, the orchestrator profile's
     intersection includes spawn / fan_out / plans.submit.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from vector.agents.profile_store import FORBIDDEN_DYNAMIC_TOOLS
from vector.agents.types import AgentSpec, RunStatus
from vector.plans.types import Plan, PlanRun, PlanStatus
from vector.tools.builder import (
    _add_orchestration_tools,
    build_registry_for,
)
from vector.tools.errors import ToolDenied
from vector.tools.files import FileGuard
from vector.tools.registry import Registry


# ---------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------


@dataclass
class _FakeRun:
    id: str
    spec: AgentSpec
    status: RunStatus = RunStatus.QUEUED


@dataclass
class _FakeManager:
    """Records every spec it's asked to spawn. Mirrors the AgentManager
    surface the orchestration tools touch — spawn() + fan_out()."""

    spawned: list[AgentSpec] = field(default_factory=list)
    _next_id: int = 0

    def _mint(self) -> str:
        self._next_id += 1
        return f"run-{self._next_id}"

    async def spawn(self, spec: AgentSpec) -> _FakeRun:
        self.spawned.append(spec)
        return _FakeRun(id=self._mint(), spec=spec, status=RunStatus.QUEUED)

    async def fan_out(self, specs: list[AgentSpec]) -> list[_FakeRun]:
        runs: list[_FakeRun] = []
        for s in specs:
            runs.append(await self.spawn(s))
        return runs


@dataclass
class _FakeRunner:
    """Records every plan submitted. Mirrors PlanRunner.submit()."""

    submitted: list[Plan] = field(default_factory=list)

    def submit(self, plan: Plan):
        self.submitted.append(plan)
        plan_run = PlanRun(plan=plan, status=PlanStatus.RUNNING)

        async def _noop() -> None:
            return None

        return plan_run, _noop()


def _registry_with_orchestration() -> tuple[Registry, _FakeManager, _FakeRunner]:
    reg = Registry()
    mgr = _FakeManager()
    runner = _FakeRunner()
    _add_orchestration_tools(reg, mgr, runner)
    return reg, mgr, runner


# ---------------------------------------------------------------------
# 1. agents.spawn: alias resolution + spec construction
# ---------------------------------------------------------------------


async def test_agent_spawn_tool_resolves_profile_alias():
    reg, mgr, _runner = _registry_with_orchestration()
    result = await reg.acall(
        "agents.spawn",
        {"name": "code", "prompt": "refactor login.py"},
    )
    assert result["name"] == "developer"
    assert result["status"] == RunStatus.QUEUED.value
    assert len(mgr.spawned) == 1
    spec = mgr.spawned[0]
    assert spec.type == "developer"
    assert spec.prompt == "refactor login.py"


async def test_agent_spawn_tool_resolves_canonical_name():
    reg, mgr, _runner = _registry_with_orchestration()
    await reg.acall(
        "agents.spawn",
        {"name": "researcher", "prompt": "find the spec"},
    )
    assert mgr.spawned[0].type == "researcher"


async def test_agent_spawn_tool_forwards_optional_fields():
    reg, mgr, _runner = _registry_with_orchestration()
    await reg.acall(
        "agents.spawn",
        {
            "name": "tester",
            "prompt": "pin the API",
            "files": ["a.py", "b.py"],
            "cost_cap_usd": 0.5,
            "timeout_s": 120,
            "success_criteria": "all tests pass",
            "max_attempts": 2,
        },
    )
    spec = mgr.spawned[0]
    assert spec.files == frozenset({"a.py", "b.py"})
    assert spec.cost_cap_usd == 0.5
    assert spec.timeout_s == 120
    assert spec.success_criteria == "all tests pass"
    assert spec.max_attempts == 2


async def test_agent_spawn_tool_rejects_unknown_profile():
    reg, _mgr, _runner = _registry_with_orchestration()
    with pytest.raises(ToolDenied, match="unknown agent profile"):
        await reg.acall(
            "agents.spawn",
            {"name": "ghost", "prompt": "do impossible things"},
        )


# ---------------------------------------------------------------------
# 2. agents.fan_out: dispatches each spec
# ---------------------------------------------------------------------


async def test_agent_fan_out_tool_dispatches_each_spec():
    reg, mgr, _runner = _registry_with_orchestration()
    result = await reg.acall(
        "agents.fan_out",
        {
            "specs": [
                {"name": "code", "prompt": "implement feature"},
                {"name": "tester", "prompt": "cover feature"},
                {"name": "security", "prompt": "audit feature"},
            ]
        },
    )
    assert len(result["runs"]) == 3
    assert len(mgr.spawned) == 3
    # Aliases resolved before the spec is built.
    types = [s.type for s in mgr.spawned]
    assert types == ["developer", "tester", "security"]
    # Order is preserved.
    names = [r["name"] for r in result["runs"]]
    assert names == ["developer", "tester", "security"]


async def test_agent_fan_out_tool_rejects_unknown_profile_in_batch():
    reg, _mgr, _runner = _registry_with_orchestration()
    with pytest.raises(ToolDenied, match="unknown agent profile"):
        await reg.acall(
            "agents.fan_out",
            {
                "specs": [
                    {"name": "code", "prompt": "ok"},
                    {"name": "phantom", "prompt": "nope"},
                ]
            },
        )


# ---------------------------------------------------------------------
# 3. plans.submit: routes the body through PlanIn + build_plan
# ---------------------------------------------------------------------


async def test_plans_submit_tool_calls_runner_submit():
    reg, _mgr, runner = _registry_with_orchestration()
    body = {
        "goal": "ship the thing",
        "steps": [
            {"id": 1, "agent": "research", "prompt": "find prior art"},
            {
                "id": 2,
                "agent": "code",
                "prompt": "draft based on {{step_1.output}}",
                "depends_on": [1],
            },
        ],
    }
    result = await reg.acall("plans.submit", body)
    assert result["status"] == PlanStatus.RUNNING.value
    assert result["plan_id"].startswith("plan-")
    assert len(runner.submitted) == 1
    plan = runner.submitted[0]
    assert plan.goal == "ship the thing"
    assert len(plan.steps) == 2
    assert plan.steps[1].depends_on == (1,)


async def test_plans_submit_tool_rejects_invalid_dag():
    reg, _mgr, _runner = _registry_with_orchestration()
    # Placeholder references step 1 but doesn't declare the dep — build_plan
    # raises PlanValidationError, which the registry surfaces as ToolError.
    bad = {
        "goal": "broken plan",
        "steps": [
            {"id": 1, "agent": "research", "prompt": "ok"},
            {
                "id": 2,
                "agent": "code",
                "prompt": "use {{step_1.output}}",
                # depends_on intentionally omitted
            },
        ],
    }
    with pytest.raises(Exception):
        await reg.acall("plans.submit", bad)


# ---------------------------------------------------------------------
# 4. Anthropic schema rendering
# ---------------------------------------------------------------------


def test_orchestration_tools_in_anthropic_schemas():
    reg, _mgr, _runner = _registry_with_orchestration()
    schemas = reg.to_anthropic_schemas()
    by_name = {s["name"]: s for s in schemas}
    assert {"agents.spawn", "agents.fan_out", "plans.submit"} == set(by_name)
    for s in schemas:
        assert isinstance(s["name"], str) and s["name"]
        assert isinstance(s["description"], str) and s["description"]
        assert s["input_schema"]["type"] == "object"
        # No top-level title field — Anthropic rejects it.
        assert "title" not in s["input_schema"]


# ---------------------------------------------------------------------
# 5. Audit gate guards: prompt_engineer can't grant these dynamically
# ---------------------------------------------------------------------


def test_forbidden_dynamic_tools_still_contains_orchestration():
    assert "agents.spawn" in FORBIDDEN_DYNAMIC_TOOLS
    assert "agents.fan_out" in FORBIDDEN_DYNAMIC_TOOLS
    assert "plans.submit" in FORBIDDEN_DYNAMIC_TOOLS


# ---------------------------------------------------------------------
# 6. End-to-end via build_registry_for: orchestrator profile sees the tools
# ---------------------------------------------------------------------


def test_orchestrator_profile_registry_intersection_includes_them(tmp_path):
    work = tmp_path / "work"
    work.mkdir(exist_ok=True)
    guard = FileGuard(read_root=tmp_path, write_root=work)
    mgr = _FakeManager()
    runner = _FakeRunner()

    reg = build_registry_for(
        "orchestrator",
        guard=guard,
        manager=mgr,
        plans_runner=runner,
    )
    names = set(reg.names())
    assert "agents.spawn" in names
    assert "agents.fan_out" in names
    assert "plans.submit" in names


def test_master_registry_omits_orchestration_when_no_manager(tmp_path):
    """Fail open: the master registry is still well-defined when the
    AgentManager isn't wired yet (e.g. during early startup)."""
    work = tmp_path / "work"
    work.mkdir(exist_ok=True)
    guard = FileGuard(read_root=tmp_path, write_root=work)

    reg = build_registry_for(
        None,  # master registry
        guard=guard,
        manager=None,
        plans_runner=None,
    )
    names = set(reg.names())
    assert "agents.spawn" not in names
    assert "agents.fan_out" not in names
    assert "plans.submit" not in names
    # Other tools still load.
    assert "file.read" in names
