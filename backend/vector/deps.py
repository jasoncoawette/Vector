from __future__ import annotations

import sqlite3
from pathlib import Path

from .config import get_settings
from .store import connect

_conn: sqlite3.Connection | None = None


def get_db() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        s = get_settings()
        path = Path(s.workspace) / "vector.db"
        _conn = connect(path)
    return _conn


def set_db(conn: sqlite3.Connection | None) -> None:
    global _conn
    _conn = conn
