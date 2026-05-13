"""Read-only telemetry tools used by the debugger profile.

Each tool wraps a store-level function; the tests here exercise the
registry-level handlers rather than the underlying SQL (which has its
own coverage). The point is to confirm the tool wiring + serialization
shape, and that the seven names land in the debugger profile's
registry without leaking into the FORBIDDEN_DYNAMIC_TOOLS list.
"""
from __future__ import annotations

import time
from pathlib import Path

import pytest

from vector.agents.profile_store import FORBIDDEN_DYNAMIC_TOOLS
from vector.store import connect
from vector.store import events as events_store
from vector.store import runs as runs_store
from vector.tools.builder import _add_debug_tools, build_registry_for
from vector.tools.files import FileGuard
from vector.tools.registry import Registry


DEBUG_TOOL_NAMES = frozenset({
    "events.recent",
    "events.by_trace",
    "audit.tail",
    "audit.by_trace",
    "runs.recent",
    "runs.get",
    "routing.stats",
})


@pytest.fixture()
def conn(tmp_path: Path):
    c = connect(tmp_path / "v.db", check_integrity=False)
    yield c
    c.close()


@pytest.fixture()
def reg(conn) -> Registry:
    """A bare Registry holding only the debug tools, bound to `conn`."""
    r = Registry()
    _add_debug_tools(r, conn)
    return r


def _seed_audit(conn, *, trace_id: str, tool: str, caller: str = "test", ok: int = 1) -> None:
    conn.execute(
        "INSERT INTO audit_log(ts, tool, caller, args_hash, result_hash, "
        "ok, reason, trace_id) VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
        (time.time(), tool, caller, "ah", "rh", ok, None, trace_id),
    )


def _run_summary(rid: str, *, status: str = "done", trace_id: str = "t1") -> dict:
    return {
        "id": rid,
        "trace_id": trace_id,
        "type": "developer",
        "prompt": "do the thing",
        "files": [],
        "status": status,
        "output": "ok",
        "error": "",
        "cost_usd": 0.01,
        "fallback_used": False,
        "attempts_used": 1,
        "max_attempts": 1,
        "last_verifier_reason": None,
    }


# ---------------------------------------------------------------------
# events.*
# ---------------------------------------------------------------------


def test_events_recent_returns_recent_events(conn, reg):
    events_store.emit(conn, "first", trace_id="t1")
    events_store.emit(conn, "second", trace_id="t1")
    events_store.emit(conn, "third", trace_id="t2")

    out = reg.call("events.recent", {"limit": 10})

    assert isinstance(out, list)
    assert len(out) == 3
    # recent() returns newest-first; third was emitted last.
    kinds = [e["kind"] for e in out]
    assert kinds[0] == "third"
    assert {"first", "second", "third"} == set(kinds)
    # Serialization shape.
    assert {"id", "ts", "trace_id", "run_id", "kind", "meta"} <= set(out[0])


def test_events_by_trace_filters_by_trace_id(conn, reg):
    events_store.emit(conn, "a", trace_id="alpha")
    events_store.emit(conn, "b", trace_id="alpha")
    events_store.emit(conn, "c", trace_id="beta")

    out = reg.call("events.by_trace", {"trace_id": "alpha"})

    assert [e["kind"] for e in out] == ["a", "b"]
    assert all(e["trace_id"] == "alpha" for e in out)


# ---------------------------------------------------------------------
# audit.*
# ---------------------------------------------------------------------


def test_audit_tail_returns_recent_rows(conn, reg):
    _seed_audit(conn, trace_id="t1", tool="file.read")
    _seed_audit(conn, trace_id="t1", tool="memory.search")

    out = reg.call("audit.tail", {"limit": 10})

    assert isinstance(out, list)
    assert len(out) == 2
    tools = {row["tool"] for row in out}
    assert tools == {"file.read", "memory.search"}


def test_audit_by_trace_filters_correctly(conn, reg):
    _seed_audit(conn, trace_id="alpha", tool="file.read")
    _seed_audit(conn, trace_id="alpha", tool="memory.search")
    _seed_audit(conn, trace_id="beta", tool="file.write")

    out = reg.call("audit.by_trace", {"trace_id": "alpha"})

    assert [row["tool"] for row in out] == ["file.read", "memory.search"]
    # Shape matches the inline /trace/{trace_id} contract.
    assert {"ts", "tool", "caller", "ok", "reason"} <= set(out[0])


# ---------------------------------------------------------------------
# runs.*
# ---------------------------------------------------------------------


def test_runs_recent_supports_status_filter(conn, reg):
    runs_store.upsert_from_summary(conn, _run_summary("r1", status="done"))
    runs_store.upsert_from_summary(conn, _run_summary("r2", status="failed"))

    all_runs = reg.call("runs.recent", {"limit": 10})
    assert {r["id"] for r in all_runs} == {"r1", "r2"}

    only_done = reg.call("runs.recent", {"limit": 10, "status": "done"})
    assert [r["id"] for r in only_done] == ["r1"]
    assert only_done[0]["status"] == "done"


def test_runs_get_returns_404_for_unknown(conn, reg):
    out = reg.call("runs.get", {"run_id": "nope-not-here"})
    assert out == {}


def test_runs_get_returns_run_when_present(conn, reg):
    runs_store.upsert_from_summary(conn, _run_summary("r1"))
    out = reg.call("runs.get", {"run_id": "r1"})
    assert out["id"] == "r1"
    assert out["status"] == "done"


# ---------------------------------------------------------------------
# routing.stats
# ---------------------------------------------------------------------


def test_routing_stats_returns_tier_summary(conn, reg):
    # Seed one outcome per tier so per_tier_summary has rows to aggregate.
    now = time.time()
    for tier in ("haiku", "sonnet", "opus"):
        conn.execute(
            "INSERT INTO routing_log(ts, agent_type, tier, model, score, "
            "source, outcome, cost_usd) VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
            (now, "developer", tier, f"model-{tier}", 0.5, "heuristic", 1, 0.01),
        )

    out = reg.call("routing.stats", {})
    assert "tiers" in out
    tiers_by_name = {t["tier"]: t for t in out["tiers"]}
    assert {"haiku", "sonnet", "opus"} <= tiers_by_name.keys()
    for name in ("haiku", "sonnet", "opus"):
        row = tiers_by_name[name]
        assert row["decisions"] >= 1
        assert row["successes"] >= 1
        # Bandit alpha/beta are always present (load_stats seeds rows).
        assert row["alpha"] >= 1.0
        assert row["beta"] >= 1.0


# ---------------------------------------------------------------------
# Profile + safety wiring
# ---------------------------------------------------------------------


def test_debugger_profile_includes_all_seven_tools(conn, tmp_path: Path):
    """Built-in debugger profile's registry must expose every debug tool."""
    guard = FileGuard(read_root=tmp_path, write_root=tmp_path / "ws")
    reg = build_registry_for("debugger", guard=guard, db=conn)
    names = set(reg.names())
    assert DEBUG_TOOL_NAMES <= names, (
        f"missing from debugger registry: {DEBUG_TOOL_NAMES - names}"
    )


def test_debug_tools_are_NOT_in_forbidden_dynamic():
    """Read-only telemetry is safe for dynamic profiles to request."""
    overlap = DEBUG_TOOL_NAMES & FORBIDDEN_DYNAMIC_TOOLS
    assert overlap == frozenset(), (
        f"debug tools must not be marked forbidden: {sorted(overlap)}"
    )
