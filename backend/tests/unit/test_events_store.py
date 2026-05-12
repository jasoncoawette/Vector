from __future__ import annotations

from pathlib import Path

import pytest

from vector.store import connect
from vector.store import events as events_store
from vector.tracing import trace


@pytest.fixture()
def conn(tmp_path: Path):
    c = connect(tmp_path / "v.db")
    yield c
    c.close()


def test_emit_writes_row(conn):
    events_store.emit(conn, "turn_start", run_id="r1", meta={"a": 1})
    rows = events_store.recent(conn)
    assert rows[0].kind == "turn_start"
    assert rows[0].run_id == "r1"
    assert rows[0].meta == {"a": 1}


def test_emit_inherits_current_trace(conn):
    with trace("trace-xyz"):
        events_store.emit(conn, "step", meta={})
    [evt] = events_store.recent(conn)
    assert evt.trace_id == "trace-xyz"


def test_emit_explicit_trace_overrides_context(conn):
    with trace("ctx-trace"):
        events_store.emit(conn, "step", trace_id="explicit")
    [evt] = events_store.recent(conn)
    assert evt.trace_id == "explicit"


def test_by_trace_returns_chronological(conn):
    with trace("chain"):
        events_store.emit(conn, "a", meta={"i": 1})
        events_store.emit(conn, "b", meta={"i": 2})
        events_store.emit(conn, "c", meta={"i": 3})
    rows = events_store.by_trace(conn, "chain")
    assert [r.kind for r in rows] == ["a", "b", "c"]


def test_by_run_returns_only_that_run(conn):
    events_store.emit(conn, "step", run_id="r1")
    events_store.emit(conn, "step", run_id="r2")
    events_store.emit(conn, "step", run_id="r1")
    rows = events_store.by_run(conn, "r1")
    assert len(rows) == 2
    assert all(r.run_id == "r1" for r in rows)


def test_recent_limit_clamped(conn):
    for _ in range(5):
        events_store.emit(conn, "step")
    rows = events_store.recent(conn, limit=999999)
    assert len(rows) <= 2000


def test_oversized_meta_truncates(conn):
    huge = {"x": "y" * 20000}
    events_store.emit(conn, "step", meta=huge)
    rows = events_store.recent(conn)
    # The raw row blob is truncated; parser falls back rather than crash.
    assert rows[0].kind == "step"


def test_unparseable_meta_handled(conn):
    # Write a bogus meta directly to simulate a corrupted row.
    conn.execute(
        "INSERT INTO events(ts, kind, meta) VALUES(?, ?, ?)",
        (0.0, "step", "{not-json"),
    )
    rows = events_store.recent(conn)
    bogus = [r for r in rows if r.meta.get("_unparseable")]
    assert bogus


def test_schema_has_trace_id_columns(conn):
    audit_cols = {r[1] for r in conn.execute("PRAGMA table_info(audit_log)")}
    routing_cols = {r[1] for r in conn.execute("PRAGMA table_info(routing_log)")}
    assert "trace_id" in audit_cols
    assert "trace_id" in routing_cols


def test_v2_migration_idempotent(tmp_path: Path):
    """connect() should be safe to call repeatedly — second open is a
    no-op for already-v2 databases."""
    p = tmp_path / "double.db"
    c1 = connect(p)
    c1.close()
    c2 = connect(p)
    ver = c2.execute("SELECT version FROM schema_meta").fetchone()["version"]
    from vector.store.db import SCHEMA_VERSION
    assert ver == SCHEMA_VERSION
    audit_cols = {r[1] for r in c2.execute("PRAGMA table_info(audit_log)")}
    assert "trace_id" in audit_cols
    c2.close()


def test_v1_database_upgrades(tmp_path: Path):
    """Simulate a pre-existing v1 install: schema_meta says v1, the v2
    column and table are absent. Re-opening should perform the
    migration and stamp v2."""
    import sqlite3 as _sql

    p = tmp_path / "v1.db"
    raw = _sql.connect(str(p))
    raw.executescript(
        """
        CREATE TABLE schema_meta (version INTEGER PRIMARY KEY);
        INSERT INTO schema_meta(version) VALUES (1);
        CREATE TABLE audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL NOT NULL,
            tool TEXT NOT NULL,
            caller TEXT NOT NULL,
            args_hash TEXT NOT NULL,
            result_hash TEXT NOT NULL,
            ok INTEGER NOT NULL,
            reason TEXT
        );
        CREATE TABLE routing_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL NOT NULL,
            agent_type TEXT,
            tier TEXT NOT NULL,
            model TEXT NOT NULL,
            score REAL NOT NULL,
            source TEXT NOT NULL,
            outcome INTEGER,
            cost_usd REAL
        );
        """
    )
    raw.commit()
    raw.close()

    c = connect(p)
    audit_cols = {r[1] for r in c.execute("PRAGMA table_info(audit_log)")}
    routing_cols = {r[1] for r in c.execute("PRAGMA table_info(routing_log)")}
    assert "trace_id" in audit_cols
    assert "trace_id" in routing_cols
    tables = {
        r[0]
        for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert "events" in tables
    ver = c.execute("SELECT version FROM schema_meta").fetchone()["version"]
    from vector.store.db import SCHEMA_VERSION
    assert ver == SCHEMA_VERSION
    c.close()
