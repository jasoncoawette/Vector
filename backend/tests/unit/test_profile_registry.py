"""Contract tests for the AgentProfile registry + dynamic profile audit.

The registry replaces the old AgentType Literal. Tests pin:
  1. Every built-in employee is present + alias-resolvable
  2. The 9-section training contract holds for task-doing employees
     (covered separately in test_agent_training.py)
  3. Validation refuses malformed profiles at construction time
  4. The dynamic-profile audit catches every dangerous mistake
     prompt_engineer could plausibly make
"""
from __future__ import annotations

import pytest

from vector.agents.profile_store import (
    FORBIDDEN_DYNAMIC_TOOLS,
    MAX_COST_CAP,
    MAX_PROMPT_LEN,
    MAX_STEP_BUDGET,
    ProfileAuditError,
    audit_blob,
    insert,
    load_active,
    revoke,
)
from vector.agents.profiles import (
    AgentProfile,
    ProfileRegistry,
    built_in_profiles,
    default_registry,
    make_default_registry,
    reset_default_registry,
)


# ---------------------------------------------------------------------
# 1. AgentProfile dataclass validation
# ---------------------------------------------------------------------


def test_profile_requires_snake_case_name():
    with pytest.raises(ValueError):
        AgentProfile(name="Bad-Name", system_prompt="x", default_tier="haiku")
    AgentProfile(name="good_name_2", system_prompt="x", default_tier="haiku")


def test_profile_rejects_unknown_tier():
    with pytest.raises(ValueError):
        AgentProfile(name="x", system_prompt="x", default_tier="gpt5")


def test_profile_rejects_out_of_range_step_budget():
    with pytest.raises(ValueError):
        AgentProfile(name="x", system_prompt="x", default_tier="haiku", step_budget=0)
    with pytest.raises(ValueError):
        AgentProfile(name="x", system_prompt="x", default_tier="haiku", step_budget=100)


def test_profile_rejects_out_of_range_cost_cap():
    with pytest.raises(ValueError):
        AgentProfile(name="x", system_prompt="x", default_tier="haiku", cost_cap_usd=0)
    with pytest.raises(ValueError):
        AgentProfile(name="x", system_prompt="x", default_tier="haiku",
                     cost_cap_usd=100)


# ---------------------------------------------------------------------
# 2. ProfileRegistry mechanics
# ---------------------------------------------------------------------


def _make(name: str, **kw) -> AgentProfile:
    return AgentProfile(
        name=name,
        system_prompt=kw.pop("system_prompt", "stub"),
        tools=kw.pop("tools", frozenset()),
        default_tier=kw.pop("default_tier", "haiku"),
        **kw,
    )


def test_register_lookup_and_iteration():
    r = ProfileRegistry()
    r.register(_make("alpha"))
    r.register(_make("beta"))
    assert r.names() == ["alpha", "beta"]
    assert r.get("alpha").name == "alpha"
    assert len(r.all_profiles()) == 2


def test_aliases_resolve():
    r = ProfileRegistry()
    r.register(_make("developer"), aliases=("code",))
    assert r.resolve("code") == "developer"
    assert r.get("code").name == "developer"
    assert "code" in r
    assert "developer" in r


def test_unknown_name_raises_keyerror():
    r = ProfileRegistry()
    with pytest.raises(KeyError):
        r.get("ghost")
    assert "ghost" not in r


def test_register_rejects_duplicate_name():
    r = ProfileRegistry()
    r.register(_make("alpha"))
    with pytest.raises(ValueError):
        r.register(_make("alpha"))


def test_register_rejects_alias_collision():
    r = ProfileRegistry()
    r.register(_make("alpha"), aliases=("a",))
    with pytest.raises(ValueError):
        r.register(_make("beta"), aliases=("a",))  # same alias
    with pytest.raises(ValueError):
        r.register(_make("a"))  # name collides with prior alias


# ---------------------------------------------------------------------
# 3. Built-in profiles
# ---------------------------------------------------------------------


EXPECTED_BUILT_INS = {
    "developer", "researcher", "writer", "tester", "security",
    "debugger", "self_healer", "prompt_engineer", "orchestrator",
}


def test_default_registry_loads_all_built_ins():
    r = make_default_registry()
    assert set(r.names()) == EXPECTED_BUILT_INS


def test_default_registry_provides_back_compat_aliases():
    r = make_default_registry()
    assert r.resolve("code") == "developer"
    assert r.resolve("research") == "researcher"


def test_default_registry_singleton_is_cached():
    reset_default_registry()
    a = default_registry()
    b = default_registry()
    assert a is b
    reset_default_registry()
    c = default_registry()
    assert c is not a


@pytest.mark.parametrize("name", sorted(EXPECTED_BUILT_INS))
def test_built_in_profile_has_nonempty_prompt_and_tools(name: str):
    profile = make_default_registry().get(name)
    assert profile.system_prompt.strip()
    # Orchestrator owns spawn/fan_out — tools may not be registered yet
    # in the live ToolRegistry, but the allowlist must be declared.
    assert len(profile.tools) > 0


def test_built_in_profiles_have_no_dynamic_flag():
    """Sanity: registry built-ins are never marked dynamic."""
    for profile in make_default_registry().all_profiles():
        assert profile.dynamic is False


def test_built_in_profiles_export_includes_aliases():
    """built_in_profiles() returns (profile, aliases) pairs — the test
    enforces that 'code' and 'research' are wired as aliases, not as
    free-standing names that compete with developer/researcher."""
    raw = built_in_profiles()
    by_name = {p.name: aliases for p, aliases in raw}
    assert "code" in by_name["developer"]
    assert "research" in by_name["researcher"]


# ---------------------------------------------------------------------
# 4. Dynamic profile audit — accept path
# ---------------------------------------------------------------------


def _ok_blob(**overrides) -> dict:
    blob = {
        "name": "investor_pdf_scraper",
        "system_prompt": "You read investor PDFs and emit a CSV-ready table.",
        "tools": ["file.read", "memory.search"],
        "default_tier": "haiku",
        "step_budget": 16,
        "cost_cap_usd": 0.5,
        "notes": "One-off PDF format.",
    }
    blob.update(overrides)
    return blob


def test_audit_accepts_minimal_valid_blob():
    available = frozenset({"file.read", "memory.search", "memory.add"})
    p = audit_blob(_ok_blob(), built_in_names=frozenset(EXPECTED_BUILT_INS),
                   available_tools=available)
    assert p.name == "investor_pdf_scraper"
    assert p.dynamic is True
    assert "file.read" in p.tools


# ---------------------------------------------------------------------
# 5. Dynamic profile audit — reject paths
# ---------------------------------------------------------------------


@pytest.mark.parametrize("forbidden_tool", sorted(FORBIDDEN_DYNAMIC_TOOLS))
def test_audit_rejects_forbidden_tools(forbidden_tool: str):
    available = frozenset({forbidden_tool, "file.read"})
    blob = _ok_blob(tools=["file.read", forbidden_tool])
    with pytest.raises(ProfileAuditError, match="forbidden"):
        audit_blob(blob, built_in_names=frozenset(),
                   available_tools=available)


def test_audit_rejects_unknown_tool():
    blob = _ok_blob(tools=["file.read", "ghosts.summon"])
    with pytest.raises(ProfileAuditError, match="unknown"):
        audit_blob(blob, built_in_names=frozenset(),
                   available_tools=frozenset({"file.read"}))


def test_audit_rejects_collision_with_built_in():
    blob = _ok_blob(name="developer")
    with pytest.raises(ProfileAuditError, match="built-in"):
        audit_blob(blob, built_in_names=frozenset({"developer"}),
                   available_tools=frozenset({"file.read", "memory.search"}))


def test_audit_rejects_long_system_prompt():
    blob = _ok_blob(system_prompt="x" * (MAX_PROMPT_LEN + 1))
    with pytest.raises(ProfileAuditError, match="longer than"):
        audit_blob(blob, built_in_names=frozenset(),
                   available_tools=frozenset({"file.read", "memory.search"}))


def test_audit_rejects_high_cost_cap():
    blob = _ok_blob(cost_cap_usd=MAX_COST_CAP + 1)
    with pytest.raises(ProfileAuditError, match="cost_cap"):
        audit_blob(blob, built_in_names=frozenset(),
                   available_tools=frozenset({"file.read", "memory.search"}))


def test_audit_rejects_high_step_budget():
    blob = _ok_blob(step_budget=MAX_STEP_BUDGET + 1)
    with pytest.raises(ProfileAuditError, match="step_budget"):
        audit_blob(blob, built_in_names=frozenset(),
                   available_tools=frozenset({"file.read", "memory.search"}))


def test_audit_rejects_bad_tier():
    blob = _ok_blob(default_tier="gpt5")
    with pytest.raises(ProfileAuditError, match="tier"):
        audit_blob(blob, built_in_names=frozenset(),
                   available_tools=frozenset({"file.read", "memory.search"}))


def test_audit_rejects_missing_keys():
    blob = _ok_blob()
    del blob["notes"]
    with pytest.raises(ProfileAuditError, match="missing"):
        audit_blob(blob, built_in_names=frozenset(),
                   available_tools=frozenset({"file.read", "memory.search"}))


def test_audit_rejects_non_object_blob():
    with pytest.raises(ProfileAuditError, match="JSON object"):
        audit_blob("not a dict",  # type: ignore[arg-type]
                   built_in_names=frozenset(),
                   available_tools=frozenset())


def test_audit_rejects_duplicate_tools():
    blob = _ok_blob(tools=["file.read", "file.read"])
    with pytest.raises(ProfileAuditError, match="duplicates"):
        audit_blob(blob, built_in_names=frozenset(),
                   available_tools=frozenset({"file.read"}))


# ---------------------------------------------------------------------
# 6. Persistence round-trip
# ---------------------------------------------------------------------


@pytest.fixture
def db(tmp_path):
    from vector.store.db import connect

    return connect(tmp_path / "vec.db", check_integrity=False)


def test_insert_and_load_active(db):
    p = audit_blob(
        _ok_blob(),
        built_in_names=frozenset(EXPECTED_BUILT_INS),
        available_tools=frozenset({"file.read", "memory.search"}),
    )
    stored = insert(db, p, created_by="run-test")
    assert stored.created_by == "run-test"
    loaded = load_active(db)
    assert len(loaded) == 1
    assert loaded[0].name == p.name
    assert loaded[0].to_profile().dynamic is True


def test_revoke_hides_from_load_active(db):
    p = audit_blob(
        _ok_blob(),
        built_in_names=frozenset(EXPECTED_BUILT_INS),
        available_tools=frozenset({"file.read", "memory.search"}),
    )
    insert(db, p, created_by="run-test")
    assert revoke(db, p.name) is True
    assert load_active(db) == []
    # second revoke is a no-op
    assert revoke(db, p.name) is False


def test_insert_refuses_built_in_profiles(db):
    # Built-ins (dynamic=False) must not land in the profiles table —
    # they're code, not data.
    built_in = AgentProfile(
        name="developer",
        system_prompt="x",
        default_tier="sonnet",
    )
    with pytest.raises(ValueError, match="dynamic"):
        insert(db, built_in)
