from __future__ import annotations

import shutil
import sqlite3
import time
from pathlib import Path

import pytest

from vector.store import connect
from vector.store.integrity import (
    DBIntegrityError,
    check,
    heal_or_raise,
    newest_snapshot,
    restore_from_snapshot,
)


def test_check_passes_on_fresh_db(tmp_path: Path):
    db = tmp_path / "v.db"
    c = connect(db, check_integrity=False)
    ok, msg = check(c)
    assert ok is True
    assert msg == "ok"
    c.close()


def test_check_fails_on_truncated_file(tmp_path: Path):
    db = tmp_path / "v.db"
    c = connect(db, check_integrity=False)
    c.execute("INSERT INTO tasks(title, source, created_at) VALUES('x', 'y', 0)")
    c.close()

    # Hard-corrupt the database: zero out the middle.
    data = bytearray(db.read_bytes())
    for i in range(100, min(len(data), 4096)):
        data[i] = 0
    db.write_bytes(bytes(data))

    raw = sqlite3.connect(str(db))
    ok, msg = check(raw)
    raw.close()
    assert ok is False
    assert "ok" not in msg


def test_newest_snapshot_picks_latest_by_mtime(tmp_path: Path):
    bdir = tmp_path / "backups"
    bdir.mkdir()
    older = bdir / "vector-20260101-0000.db"
    newer = bdir / "vector-20260102-0000.db"
    older.write_text("x")
    newer.write_text("y")
    # Force mtimes.
    import os

    os.utime(older, (1000, 1000))
    os.utime(newer, (2000, 2000))
    assert newest_snapshot(bdir) == newer


def test_newest_snapshot_returns_none_when_empty(tmp_path: Path):
    assert newest_snapshot(tmp_path / "nope") is None
    bdir = tmp_path / "empty"
    bdir.mkdir()
    assert newest_snapshot(bdir) is None


def test_restore_copies_snapshot_and_moves_corrupt_aside(tmp_path: Path):
    db = tmp_path / "v.db"
    bdir = tmp_path / "backups"
    bdir.mkdir()
    snap = bdir / "vector-20260101-0000.db"
    db.write_text("corrupt")
    snap.write_text("clean")
    # Also stage a -wal sidecar to ensure it moves too.
    wal = Path(str(db) + "-wal")
    wal.write_text("wal-data")

    moved = restore_from_snapshot(db, bdir)
    assert moved is not None
    assert db.read_text() == "clean"
    # The corrupted main file landed at moved-path; the wal landed
    # alongside with the -wal suffix preserved.
    assert moved.exists()
    assert (moved.parent / (moved.name + "-wal")).exists() or Path(
        str(moved) + "-wal"
    ).exists()


def test_restore_returns_none_when_no_snapshot(tmp_path: Path):
    db = tmp_path / "v.db"
    db.write_text("corrupt")
    bdir = tmp_path / "backups"
    bdir.mkdir()
    assert restore_from_snapshot(db, bdir) is None
    # db left in place because there was nothing to restore from.
    assert db.read_text() == "corrupt"


def test_heal_or_raise_passes_through_healthy(tmp_path: Path):
    db = tmp_path / "v.db"
    # Build a real DB so heal_or_raise can open it.
    c = connect(db, check_integrity=False)
    c.close()
    bdir = tmp_path / "backups"
    bdir.mkdir()
    conn = heal_or_raise(db, backup_dir=bdir)
    ok, _ = check(conn)
    assert ok is True
    conn.close()


def test_heal_or_raise_restores_from_snapshot(tmp_path: Path):
    db = tmp_path / "v.db"
    bdir = tmp_path / "backups"
    bdir.mkdir()

    # Create a good snapshot via connect().
    snap_src = tmp_path / "snap-src.db"
    c = connect(snap_src, check_integrity=False)
    c.execute(
        "INSERT INTO tasks(title, source, created_at) VALUES('saved', 'snap', 0)"
    )
    c.close()
    shutil.copy(snap_src, bdir / "vector-20260101-0000.db")

    # Corrupt the live db.
    db.write_bytes(b"\x00" * 2048)

    conn = heal_or_raise(db, backup_dir=bdir)
    rows = conn.execute("SELECT title FROM tasks").fetchall()
    assert any(r[0] == "saved" for r in rows)
    conn.close()


def test_heal_or_raise_raises_when_no_snapshot(tmp_path: Path):
    db = tmp_path / "v.db"
    db.write_bytes(b"\x00" * 2048)
    bdir = tmp_path / "backups"
    bdir.mkdir()
    with pytest.raises(DBIntegrityError, match="no snapshot"):
        heal_or_raise(db, backup_dir=bdir)


def test_heal_or_raise_raises_when_snapshot_also_corrupt(tmp_path: Path):
    db = tmp_path / "v.db"
    db.write_bytes(b"\x00" * 2048)
    bdir = tmp_path / "backups"
    bdir.mkdir()
    (bdir / "vector-20260101-0000.db").write_bytes(b"\x00" * 2048)
    with pytest.raises(DBIntegrityError, match="snapshot also"):
        heal_or_raise(db, backup_dir=bdir)


def test_connect_runs_integrity_check_by_default(tmp_path: Path):
    """End-to-end: a corrupted live DB plus a good snapshot recovers."""
    db = tmp_path / "v.db"
    bdir = tmp_path / "backups"
    bdir.mkdir()

    # Snapshot setup.
    snap_src = tmp_path / "src.db"
    c = connect(snap_src, check_integrity=False)
    c.execute(
        "INSERT INTO tasks(title, source, created_at) VALUES('snapshotted', 'x', 0)"
    )
    c.close()
    shutil.copy(snap_src, bdir / "vector-20260101-0000.db")

    db.write_bytes(b"\x00" * 2048)

    import os

    os.environ["VECTOR_BACKUP_DIR"] = str(bdir)
    try:
        conn = connect(db)
        rows = conn.execute("SELECT title FROM tasks").fetchall()
        assert any(r[0] == "snapshotted" for r in rows)
        conn.close()
    finally:
        os.environ.pop("VECTOR_BACKUP_DIR", None)
