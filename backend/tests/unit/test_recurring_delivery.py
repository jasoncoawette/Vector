"""Smoke tests for the resumed scheduler / preferences / voice_inbox stack.

Covers the architectural seams added in RES-43:
  - schema v5 creates the three new tables on a fresh DB
  - preferences store roundtrips (set/get/clear)
  - inbox enqueues + drains with delivered_at gating
  - master registry exposes preferences.* tools when db is set
  - sub-agent profiles do NOT get preferences.* via the allowlist intersection
  - FORBIDDEN_DYNAMIC_TOOLS denies them to dynamic profiles
"""
from __future__ import annotations

import sqlite3
import time

import pytest

from vector.agents.profile_store import FORBIDDEN_DYNAMIC_TOOLS
from vector.agents.profiles import default_registry, reset_default_registry
from vector.store import inbox as inbox_store
from vector.store import preferences as prefs_store
from vector.store.db import SCHEMA_VERSION, connect
from vector.tools.builder import build_registry_for
from vector.tools.files import FileGuard


@pytest.fixture
def db(tmp_path):
    p = tmp_path / "vector.db"
    return connect(p, check_integrity=False)


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name = ?",
        (name,),
    ).fetchone()
    return row is not None


def test_v5_creates_recurring_tables(db):
    assert SCHEMA_VERSION == 5
    assert _table_exists(db, "preferences")
    assert _table_exists(db, "voice_inbox")
    assert _table_exists(db, "scheduler_log")
    # v4 still produces the profiles table — we didn't remove it.
    assert _table_exists(db, "profiles")
    ver = db.execute("SELECT version FROM schema_meta").fetchone()["version"]
    assert ver == 5


def test_preferences_roundtrip(db):
    p = prefs_store.set_(db, "daily_brief", {"enabled": True, "time": "07:00"})
    assert p.value == {"enabled": True, "time": "07:00"}
    got = prefs_store.get(db, "daily_brief")
    assert got is not None and got.value["time"] == "07:00"
    deleted = prefs_store.clear(db, "daily_brief")
    assert deleted == 1
    assert prefs_store.get(db, "daily_brief") is None


def test_inbox_enqueue_and_drain(db):
    msg_id = inbox_store.enqueue(db, kind="daily_brief", text="Hi.", meta={"k": 1})
    pending = inbox_store.pending(db)
    assert len(pending) == 1 and pending[0].id == msg_id
    inbox_store.mark_delivered(db, msg_id)
    assert inbox_store.pending(db) == []


def test_master_registry_exposes_preferences_when_db_set(db, tmp_path):
    guard = FileGuard(read_root=tmp_path, write_root=tmp_path)
    reg = build_registry_for(None, guard=guard, db=db)
    assert "preferences.set" in reg.names()
    assert "preferences.get" in reg.names()
    assert "preferences.clear" in reg.names()


def test_developer_profile_does_not_get_preferences(db, tmp_path):
    reset_default_registry()
    guard = FileGuard(read_root=tmp_path, write_root=tmp_path)
    reg = build_registry_for("developer", guard=guard, db=db)
    names = reg.names()
    assert "preferences.set" not in names
    assert "preferences.get" not in names
    assert "preferences.clear" not in names


def test_preferences_tools_in_forbidden_dynamic():
    assert "preferences.set" in FORBIDDEN_DYNAMIC_TOOLS
    assert "preferences.get" in FORBIDDEN_DYNAMIC_TOOLS
    assert "preferences.clear" in FORBIDDEN_DYNAMIC_TOOLS


def test_no_built_in_profile_lists_preferences():
    reset_default_registry()
    for profile in default_registry().all_profiles():
        for tool in profile.tools:
            assert not tool.startswith("preferences."), (
                f"profile {profile.name!r} unexpectedly lists {tool!r}; "
                "preferences.* belong to the voice brain only"
            )
