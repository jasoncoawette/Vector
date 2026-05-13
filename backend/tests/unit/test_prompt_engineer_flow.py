"""End-to-end tests for the dynamic-profile minting flow (RES-42).

The orchestrator can spawn prompt_engineer for a profile design,
then call profiles.audit_and_insert to audit + persist + register
the engineer's JSON reply. These tests pin:

  1. audit_and_insert_and_register helper: happy path, audit reject,
     name collision, forbidden tool, registry rollback.
  2. Tool surface: invalid JSON returns a structured {ok: false} reply,
     not a raised ToolError.
  3. Audit gate: profiles.audit_and_insert is in FORBIDDEN_DYNAMIC_TOOLS
     so a dynamic profile can never request it.
  4. Wiring: the orchestrator's master registry includes the tool when
     profile_admin=True; other agents' registries do not.
  5. Integration: a fake brain that emits the three-step orchestrator
     loop (spawn engineer → audit_and_insert → spawn new agent) ends
     with the new profile registered AND spawnable by the manager.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from vector.agents.profile_store import (
    FORBIDDEN_DYNAMIC_TOOLS,
    audit_and_insert_and_register,
    load_active,
)
from vector.agents.profiles import (
    default_registry,
    make_default_registry,
    reset_default_registry,
)
from vector.agents.types import AgentSpec, RunStatus
from vector.plans.types import Plan, PlanRun, PlanStatus
from vector.tools.builder import build_registry_for
from vector.tools.files import FileGuard


_AVAILABLE_TOOLS = frozenset(
    {"file.read", "memory.search", "memory.add", "obsidian.read"}
)


def _ok_blob(**overrides) -> dict:
    blob = {
        "name": "transcript_summarizer",
        "system_prompt": "You read meeting transcript files and emit a "
                         "5-bullet summary plus action items.",
        "tools": ["file.read", "memory.search"],
        "default_tier": "haiku",
        "step_budget": 10,
        "cost_cap_usd": 0.3,
        "notes": "One-off when no other agent fits.",
    }
    blob.update(overrides)
    return blob


@pytest.fixture
def db(tmp_path: Path):
    from vector.store.db import connect

    return connect(tmp_path / "vec.db", check_integrity=False)


@pytest.fixture(autouse=True)
def _isolate_default_registry():
    """The audit_and_insert tool mutates the singleton registry. Reset
    before AND after each test so cross-test ordering doesn't matter."""
    reset_default_registry()
    yield
    reset_default_registry()


# ---------------------------------------------------------------------
# 1. Helper: happy path + every failure mode
# ---------------------------------------------------------------------


def test_audit_and_insert_happy_path(db):
    registry = make_default_registry()
    blob = _ok_blob()

    ok, reason, name = audit_and_insert_and_register(
        blob,
        conn=db,
        registry=registry,
        available_tools=_AVAILABLE_TOOLS,
        created_by="run-test",
    )
    assert ok is True
    assert reason == "loaded"
    assert name == "transcript_summarizer"

    # Profile is now in the registry, with dynamic=True.
    loaded = registry.get("transcript_summarizer")
    assert loaded.dynamic is True
    assert "file.read" in loaded.tools

    # Row landed in the DB.
    rows = load_active(db)
    assert any(r.name == "transcript_summarizer" for r in rows)


def test_audit_and_insert_rejects_invalid_blob(db):
    """Missing required key → audit fails BEFORE any DB write."""
    registry = make_default_registry()
    bad = _ok_blob()
    del bad["system_prompt"]

    ok, reason, name = audit_and_insert_and_register(
        bad,
        conn=db,
        registry=registry,
        available_tools=_AVAILABLE_TOOLS,
    )
    assert ok is False
    assert "system_prompt" in reason
    assert name is None

    # Nothing in the registry.
    assert "transcript_summarizer" not in registry
    # Nothing in the DB.
    assert load_active(db) == []


def test_audit_and_insert_rejects_built_in_name_collision(db):
    """The audit gate refuses to overwrite a built-in name."""
    registry = make_default_registry()
    blob = _ok_blob(name="developer")

    ok, reason, name = audit_and_insert_and_register(
        blob,
        conn=db,
        registry=registry,
        available_tools=_AVAILABLE_TOOLS,
    )
    assert ok is False
    assert "built-in" in reason or "developer" in reason
    assert name is None

    # 'developer' is still the built-in (dynamic=False), unchanged.
    assert registry.get("developer").dynamic is False
    # No row inserted under the colliding name.
    assert load_active(db) == []


def test_audit_and_insert_rejects_forbidden_tool(db):
    """file.delete is in FORBIDDEN_DYNAMIC_TOOLS — audit refuses."""
    registry = make_default_registry()
    blob = _ok_blob(tools=["file.read", "file.delete"])

    ok, reason, name = audit_and_insert_and_register(
        blob,
        conn=db,
        registry=registry,
        available_tools=_AVAILABLE_TOOLS | {"file.delete"},
    )
    assert ok is False
    assert "forbidden" in reason or "file.delete" in reason
    assert name is None
    assert load_active(db) == []


def test_audit_and_insert_rolls_back_registry_failure(db, monkeypatch):
    """If audit + insert succeed but registry.register raises, the
    just-inserted row is revoked so the DB doesn't carry a row that
    the registry can't see. Pins the rollback path."""
    registry = make_default_registry()
    blob = _ok_blob()

    original_register = registry.register

    def _explode(profile, *, aliases=()):
        raise ValueError("simulated in-memory collision")

    monkeypatch.setattr(registry, "register", _explode)

    ok, reason, name = audit_and_insert_and_register(
        blob,
        conn=db,
        registry=registry,
        available_tools=_AVAILABLE_TOOLS,
    )
    assert ok is False
    assert "simulated" in reason
    assert name is None

    # The row was inserted but immediately revoked, so load_active hides it.
    active = load_active(db)
    assert all(r.name != "transcript_summarizer" for r in active)

    # The patched register was the failing one — registry doesn't carry it.
    monkeypatch.setattr(registry, "register", original_register)
    assert "transcript_summarizer" not in registry


# ---------------------------------------------------------------------
# 2. Tool surface: bad JSON becomes a structured reply, not a raise
# ---------------------------------------------------------------------


def test_audit_and_insert_tool_handles_invalid_json(db, tmp_path):
    work = tmp_path / "work"
    work.mkdir(exist_ok=True)
    guard = FileGuard(read_root=tmp_path, write_root=work)

    reg = build_registry_for(
        "orchestrator",
        guard=guard,
        db=db,
        profile_admin=True,
    )
    assert "profiles.audit_and_insert" in reg.names()

    result = reg.call("profiles.audit_and_insert", {"blob_json": "not json"})
    assert result["ok"] is False
    assert result["reason"].startswith("invalid JSON")
    assert result["name"] is None


# ---------------------------------------------------------------------
# 3. Audit gate: forbidden-list contains the new tool
# ---------------------------------------------------------------------


def test_profiles_audit_and_insert_in_FORBIDDEN_DYNAMIC_TOOLS():
    assert "profiles.audit_and_insert" in FORBIDDEN_DYNAMIC_TOOLS


# ---------------------------------------------------------------------
# 4. Wiring: orchestrator gets the tool; others don't
# ---------------------------------------------------------------------


def test_orchestrator_registry_includes_audit_tool(db, tmp_path):
    work = tmp_path / "work"
    work.mkdir(exist_ok=True)
    guard = FileGuard(read_root=tmp_path, write_root=work)

    reg = build_registry_for(
        "orchestrator",
        guard=guard,
        db=db,
        profile_admin=True,
    )
    assert "profiles.audit_and_insert" in reg.names()


def test_non_orchestrator_registry_excludes_audit_tool(db, tmp_path):
    work = tmp_path / "work"
    work.mkdir(exist_ok=True)
    guard = FileGuard(read_root=tmp_path, write_root=work)

    reg = build_registry_for(
        "developer",
        guard=guard,
        db=db,
        profile_admin=False,
    )
    assert "profiles.audit_and_insert" not in reg.names()


def test_master_registry_excludes_audit_tool_without_flag(db, tmp_path):
    """Even with db wired, the master registry omits the tool unless
    profile_admin=True. Belt-and-suspenders gate."""
    work = tmp_path / "work"
    work.mkdir(exist_ok=True)
    guard = FileGuard(read_root=tmp_path, write_root=work)

    reg = build_registry_for(
        None,  # master
        guard=guard,
        db=db,
        profile_admin=False,
    )
    assert "profiles.audit_and_insert" not in reg.names()


# ---------------------------------------------------------------------
# 5. Integration: simulate the orchestrator's three-step minting flow
# ---------------------------------------------------------------------


@dataclass
class _FakeRun:
    id: str
    spec: AgentSpec
    status: RunStatus = RunStatus.QUEUED


@dataclass
class _FakeManager:
    """Records every spec it's asked to spawn. Mirrors AgentManager."""
    spawned: list[AgentSpec] = field(default_factory=list)
    _next_id: int = 0

    def _mint(self) -> str:
        self._next_id += 1
        return f"run-{self._next_id}"

    async def spawn(self, spec: AgentSpec) -> _FakeRun:
        self.spawned.append(spec)
        return _FakeRun(id=self._mint(), spec=spec)


@dataclass
class _FakeRunner:
    """Mirrors PlanRunner.submit so build_registry_for accepts it."""
    submitted: list[Plan] = field(default_factory=list)

    def submit(self, plan: Plan):
        self.submitted.append(plan)
        plan_run = PlanRun(plan=plan, status=PlanStatus.RUNNING)

        async def _noop() -> None:
            return None

        return plan_run, _noop()


async def test_orchestrator_full_flow_via_fake_brain(db, tmp_path):
    """Walk the orchestrator's three-step minting loop through the
    actual tool registry. We don't need a real brain or executor —
    the contract under test is: handing a valid JSON blob through the
    profiles.audit_and_insert tool gets it persisted + registered, and
    the manager can then spawn it by name.
    """
    work = tmp_path / "work"
    work.mkdir(exist_ok=True)
    guard = FileGuard(read_root=tmp_path, write_root=work)
    mgr = _FakeManager()
    runner = _FakeRunner()

    reg = build_registry_for(
        "orchestrator",
        guard=guard,
        db=db,
        manager=mgr,
        plans_runner=runner,
        profile_admin=True,
    )
    # Sanity: orchestrator profile sees all four tools.
    for tool in (
        "agents.spawn", "agents.fan_out", "plans.submit",
        "profiles.audit_and_insert",
    ):
        assert tool in reg.names()

    # --- Step 1: orchestrator spawns prompt_engineer.
    spawn_engineer = await reg.acall(
        "agents.spawn",
        {
            "name": "prompt_engineer",
            "prompt": "I need an agent that summarizes meeting transcripts.",
        },
    )
    assert spawn_engineer["name"] == "prompt_engineer"
    assert mgr.spawned[-1].type == "prompt_engineer"

    # --- Step 2: pretend prompt_engineer returned this JSON; orchestrator
    # forwards it to profiles.audit_and_insert. The blob's `tools` must
    # be a subset of the master registry's wired tools (file.read +
    # debug tools were registered above; memory/obsidian were not).
    engineer_reply = json.dumps(
        _ok_blob(
            name="meeting_summarizer",
            tools=["file.read", "events.recent"],
        )
    )
    audit_reply = reg.call(
        "profiles.audit_and_insert",
        {"blob_json": engineer_reply},
    )
    assert audit_reply["ok"] is True, audit_reply["reason"]
    assert audit_reply["reason"] == "loaded"
    new_name = audit_reply["name"]
    assert new_name == "meeting_summarizer"

    # --- Step 3: orchestrator spawns the freshly-minted profile.
    spawn_new = await reg.acall(
        "agents.spawn",
        {"name": new_name, "prompt": "Summarize the 2026-05-12 standup."},
    )
    assert spawn_new["name"] == new_name
    assert mgr.spawned[-1].type == new_name
    assert mgr.spawned[-1].prompt == "Summarize the 2026-05-12 standup."

    # The registry now resolves the dynamic profile.
    assert new_name in default_registry()
    assert default_registry().get(new_name).dynamic is True

    # And the row is on disk.
    assert any(r.name == new_name for r in load_active(db))


async def test_orchestrator_full_flow_audit_failure_surfaces_reason(
    db, tmp_path
):
    """When the engineer's blob fails audit, the tool returns ok=false
    with a reason — never raises. The orchestrator can then ask the
    engineer for a revision."""
    work = tmp_path / "work"
    work.mkdir(exist_ok=True)
    guard = FileGuard(read_root=tmp_path, write_root=work)
    mgr = _FakeManager()
    runner = _FakeRunner()

    reg = build_registry_for(
        "orchestrator",
        guard=guard,
        db=db,
        manager=mgr,
        plans_runner=runner,
        profile_admin=True,
    )

    # Bad blob: the engineer accidentally requested file.delete.
    bad_reply = json.dumps(
        _ok_blob(name="reckless_agent", tools=["file.read", "file.delete"])
    )
    result = reg.call(
        "profiles.audit_and_insert",
        {"blob_json": bad_reply},
    )
    assert result["ok"] is False
    assert "file.delete" in result["reason"] or "forbidden" in result["reason"]
    assert result["name"] is None
    # No registration happened — the engineer can revise and retry.
    assert "reckless_agent" not in default_registry()
