from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

SCHEMA_VERSION = 2

# v1 — initial schema. All CREATE TABLE IF NOT EXISTS so it's safe to
# replay on every connect (idempotent).
_V1_SQL = """
CREATE TABLE IF NOT EXISTS schema_meta (
    version INTEGER PRIMARY KEY
);
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    external_id TEXT UNIQUE,
    title TEXT NOT NULL,
    source TEXT NOT NULL,
    tag TEXT NOT NULL DEFAULT 'process',
    priority INTEGER NOT NULL DEFAULT 3,
    mission TEXT NOT NULL DEFAULT 'stratus',
    status TEXT NOT NULL DEFAULT 'open',
    shipped_at REAL,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS picks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    day TEXT NOT NULL,
    rank INTEGER NOT NULL,
    task_id INTEGER NOT NULL,
    reason TEXT NOT NULL,
    score REAL NOT NULL,
    accepted INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY (task_id) REFERENCES tasks(id)
);
CREATE TABLE IF NOT EXISTS overrides (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    day TEXT NOT NULL,
    removed_task_id INTEGER NOT NULL,
    added_task_id INTEGER NOT NULL,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS picker_weights (
    feature TEXT PRIMARY KEY,
    weight REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    section TEXT NOT NULL,
    name TEXT NOT NULL,
    value REAL NOT NULL,
    unit TEXT,
    recorded_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_metrics_lookup
    ON metrics(section, name, recorded_at DESC);
CREATE TABLE IF NOT EXISTS reviews (
    day TEXT PRIMARY KEY,
    shipped_ids TEXT NOT NULL,
    slipped_ids TEXT NOT NULL,
    note TEXT,
    recorded_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    text TEXT NOT NULL,
    embedding BLOB NOT NULL,
    meta TEXT,
    recorded_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_memories_kind ON memories(kind);
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    tool TEXT NOT NULL,
    caller TEXT NOT NULL,
    args_hash TEXT NOT NULL,
    result_hash TEXT NOT NULL,
    ok INTEGER NOT NULL,
    reason TEXT
);
CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_log(ts DESC);
CREATE TABLE IF NOT EXISTS choke_points (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    week TEXT NOT NULL,
    rank INTEGER NOT NULL,
    title TEXT NOT NULL,
    note TEXT,
    recorded_at REAL NOT NULL,
    UNIQUE(week, rank)
);
CREATE TABLE IF NOT EXISTS routing_bandit (
    tier TEXT PRIMARY KEY,
    alpha REAL NOT NULL DEFAULT 1.0,
    beta REAL NOT NULL DEFAULT 1.0,
    trials INTEGER NOT NULL DEFAULT 0,
    updated_at REAL NOT NULL DEFAULT 0.0
);
CREATE TABLE IF NOT EXISTS routing_log (
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
CREATE INDEX IF NOT EXISTS idx_routing_log_ts ON routing_log(ts DESC);
"""

# v2 — add trace_id to existing tables, create the events table.
# Column adds are guarded because SQLite has no ADD COLUMN IF NOT EXISTS.
_V2_NEW_TABLES = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    trace_id TEXT,
    run_id TEXT,
    kind TEXT NOT NULL,
    cost_delta REAL,
    latency_ms REAL,
    meta TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_trace ON events(trace_id, ts);
CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts DESC);
CREATE INDEX IF NOT EXISTS idx_events_run ON events(run_id, ts);
"""


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r[1] == column for r in rows)


def _add_column_if_missing(
    conn: sqlite3.Connection, table: str, column: str, decl: str
) -> None:
    if not _column_exists(conn, table, column):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    _migrate(conn)
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    # v1 is always replayed (idempotent — only CREATE IF NOT EXISTS).
    conn.executescript(_V1_SQL)

    cur = conn.execute("SELECT version FROM schema_meta")
    row = cur.fetchone()
    if row is None:
        conn.execute("INSERT INTO schema_meta(version) VALUES (?)", (1,))
        current = 1
    else:
        current = int(row["version"])

    if current < 2:
        conn.executescript(_V2_NEW_TABLES)
        _add_column_if_missing(conn, "audit_log", "trace_id", "TEXT")
        _add_column_if_missing(conn, "routing_log", "trace_id", "TEXT")
        conn.execute("UPDATE schema_meta SET version = ?", (2,))


@contextmanager
def tx(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    conn.execute("BEGIN")
    try:
        yield conn
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
