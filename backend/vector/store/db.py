from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

SCHEMA_VERSION = 1

_MIGRATIONS: list[str] = [
    """
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
    """,
]


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    _migrate(conn)
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    conn.executescript(_MIGRATIONS[0])
    cur = conn.execute("SELECT version FROM schema_meta")
    row = cur.fetchone()
    if row is None:
        conn.execute("INSERT INTO schema_meta(version) VALUES (?)", (SCHEMA_VERSION,))


@contextmanager
def tx(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    conn.execute("BEGIN")
    try:
        yield conn
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
