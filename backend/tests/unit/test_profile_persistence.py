"""Boot-time merge of persisted dynamic profiles into the registry.

Built-in profiles live in code. The prompt_engineer agent can produce
dynamic profiles that get audited + persisted to the `profiles` table —
but the registry never reads from that table at startup, so dynamic
profiles inserted in one run die at the next restart.

These tests pin the new wiring:
  - register_persisted() merges active rows into a fresh registry
  - revoked rows stay out
  - name collisions never overwrite a built-in (the built-in wins)
  - every decision is logged
  - the FastAPI startup hook actually calls register_persisted
"""
from __future__ import annotations

import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from vector import audit
from vector.agents.profile_store import audit_blob, insert, revoke
from vector.agents.profiles import (
    AgentProfile,
    ProfileRegistry,
    default_registry,
    make_default_registry,
    register_persisted,
    reload_persisted,
    reset_default_registry,
)


EXPECTED_BUILT_INS = frozenset({
    "developer", "researcher", "writer", "tester", "security",
    "debugger", "self_healer", "prompt_engineer", "orchestrator",
})

_AVAILABLE_TOOLS = frozenset({"file.read", "memory.search", "memory.add"})


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


def _insert_blob(db, **overrides) -> str:
    profile = audit_blob(
        _ok_blob(**overrides),
        built_in_names=EXPECTED_BUILT_INS,
        available_tools=_AVAILABLE_TOOLS,
    )
    insert(db, profile, created_by="run-test")
    return profile.name


@pytest.fixture
def db(tmp_path: Path):
    from vector.store.db import connect

    return connect(tmp_path / "vec.db", check_integrity=False)


# ---------------------------------------------------------------------
# 1. register_persisted merges active rows
# ---------------------------------------------------------------------


def test_register_persisted_loads_active_profiles(db):
    name = _insert_blob(db)
    registry = make_default_registry()
    assert name not in registry

    outcomes = register_persisted(registry, db)
    assert outcomes == {name: "loaded"}
    assert name in registry
    loaded = registry.get(name)
    assert loaded.dynamic is True
    assert "file.read" in loaded.tools


def test_register_persisted_skips_revoked(db):
    name = _insert_blob(db)
    assert revoke(db, name) is True

    registry = make_default_registry()
    outcomes = register_persisted(registry, db)
    assert outcomes == {}
    assert name not in registry


def test_register_persisted_skips_built_in_name_collision(db):
    """A persisted row with the same name as a pre-registered profile
    must be skipped — built-ins always win on collision."""
    registry = ProfileRegistry()
    builtin = AgentProfile(
        name="ghost",
        system_prompt="ghost-builtin",
        default_tier="haiku",
        tools=frozenset({"file.read"}),
    )
    registry.register(builtin)

    # Audit-gate forbids names that match real built-ins, but the
    # registry itself doesn't know about audit. We construct a stored
    # row that uses the same name as the pre-registered "ghost".
    profile = audit_blob(
        _ok_blob(name="ghost"),
        built_in_names=EXPECTED_BUILT_INS,  # "ghost" isn't a built-in
        available_tools=_AVAILABLE_TOOLS,
    )
    insert(db, profile, created_by="run-test")

    outcomes = register_persisted(registry, db)
    assert "ghost" in outcomes
    assert outcomes["ghost"].startswith("skipped:")
    # Pre-registered profile is preserved unchanged.
    assert registry.get("ghost").system_prompt == "ghost-builtin"
    assert registry.get("ghost").dynamic is False


def test_register_persisted_logs_outcomes(db, caplog):
    """Each row produces an INFO (load) or WARNING (skip) log record."""
    loaded_name = _insert_blob(db, name="loaded_one")

    # A second row that will collide → skipped.
    registry = ProfileRegistry()
    registry.register(
        AgentProfile(
            name="collider",
            system_prompt="x",
            default_tier="haiku",
            tools=frozenset({"file.read"}),
        )
    )
    profile = audit_blob(
        _ok_blob(name="collider"),
        built_in_names=EXPECTED_BUILT_INS,
        available_tools=_AVAILABLE_TOOLS,
    )
    insert(db, profile, created_by="run-test")

    with caplog.at_level(logging.INFO, logger="vector.profiles"):
        outcomes = register_persisted(registry, db)

    assert outcomes[loaded_name] == "loaded"
    assert outcomes["collider"].startswith("skipped:")

    records = [r for r in caplog.records if r.name == "vector.profiles"]
    assert len(records) == 2
    levels = {r.levelno for r in records}
    assert logging.INFO in levels
    assert logging.WARNING in levels


def test_register_persisted_returns_empty_when_no_rows(db):
    registry = make_default_registry()
    assert register_persisted(registry, db) == {}


def test_reload_persisted_resets_and_remerges(db):
    name = _insert_blob(db)
    reset_default_registry()
    # Before reload: built-in only, dynamic name is absent.
    assert name not in default_registry()

    reload_persisted(db)
    assert name in default_registry()


# ---------------------------------------------------------------------
# 2. App startup hook wiring
# ---------------------------------------------------------------------


def test_startup_hook_calls_register_persisted(tmp_path: Path):
    """TestClient(app) triggers the FastAPI startup hook on the first
    request. If a profile is in the DB before that fires, it should be
    resolvable via default_registry() afterwards."""
    from vector.store import connect
    from vector.deps import set_db

    # Build a DB out-of-band so we can seed it before startup runs.
    conn = connect(tmp_path / "vec.db", check_integrity=False)
    name = _insert_blob(conn)

    # Wire the seeded DB into deps and reset the registry singleton so
    # startup builds + merges fresh.
    set_db(conn)
    reset_default_registry()

    from vector.app import app

    try:
        with TestClient(app) as client:
            # First request triggers startup.
            assert client.get("/healthz").status_code == 200
            assert name in default_registry()
            loaded = default_registry().get(name)
            assert loaded.dynamic is True
    finally:
        audit.set_sink(None)
        set_db(None)
        reset_default_registry()
        conn.close()
