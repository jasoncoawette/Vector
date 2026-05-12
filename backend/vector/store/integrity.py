"""SQLite integrity check + restore-from-snapshot recovery.

Called once at startup. Runs `PRAGMA integrity_check`; if it fails:
  1. Move the corrupted file aside (vector.db.corrupt-YYYYMMDD-HHMM)
  2. Find the newest snapshot in VECTOR_BACKUP_DIR (default
     ~/VectorBackups)
  3. Copy it into place
  4. Re-open and re-check — if it still fails, raise

This is what makes the database 'self-healing': a corrupted DB no
longer wedges the backend across restarts. Snapshot rotation lives
in ops/snapshot.sh; this module only reads the directory.
"""
from __future__ import annotations

import logging
import os
import shutil
import sqlite3
import time
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("vector.store.integrity")


class DBIntegrityError(RuntimeError):
    """Raised when the database is corrupt and we have no usable snapshot."""


def check(conn: sqlite3.Connection) -> tuple[bool, str]:
    """Run PRAGMA integrity_check and return (ok, message).

    The pragma is fast on small DBs (<100MB) and runs offline-safe."""
    try:
        rows = conn.execute("PRAGMA integrity_check").fetchall()
    except sqlite3.DatabaseError as e:
        return False, f"pragma failed: {e}"
    if not rows:
        return False, "no rows returned"
    # SQLite returns one row with text "ok" when healthy, otherwise
    # one row per problem.
    first = rows[0][0]
    if first == "ok":
        return True, "ok"
    return False, "; ".join(str(r[0]) for r in rows[:5])


def newest_snapshot(backup_dir: Path) -> Path | None:
    """Return the path to the newest vector-*.db snapshot, or None."""
    if not backup_dir.is_dir():
        return None
    candidates = sorted(
        backup_dir.glob("vector-*.db"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def restore_from_snapshot(db_path: Path, backup_dir: Path) -> Path | None:
    """Move the corrupted db aside and copy in the newest snapshot.

    Returns the path of the corrupted file that was moved aside, or
    None if no snapshot was available."""
    snap = newest_snapshot(backup_dir)
    if snap is None:
        return None
    stamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    corrupt_path = db_path.with_suffix(f".db.corrupt-{stamp}")
    # Also move the WAL + SHM sidecars so the restored db isn't
    # silently merged with corrupted journal contents.
    for suffix in ("", "-wal", "-shm"):
        side = Path(str(db_path) + suffix)
        if side.exists():
            shutil.move(str(side), str(corrupt_path) + suffix)
    shutil.copy2(str(snap), str(db_path))
    logger.warning(
        "restored db from snapshot",
        extra={
            "snapshot": str(snap),
            "corrupt_path": str(corrupt_path),
            "snapshot_age_s": time.time() - snap.stat().st_mtime,
        },
    )
    return corrupt_path


def heal_or_raise(
    db_path: Path,
    *,
    backup_dir: Path | None = None,
    open_conn: "callable[[Path], sqlite3.Connection] | None" = None,
) -> sqlite3.Connection:
    """Open db_path, run integrity_check, restore from snapshot if
    corrupted, re-check. Returns a healthy connection or raises.

    `open_conn` is injected for tests; in production we just call
    `sqlite3.connect(...)` with the same flags `store.db.connect` uses.
    """
    if backup_dir is None:
        backup_dir = Path(
            os.environ.get("VECTOR_BACKUP_DIR", str(Path.home() / "VectorBackups"))
        )
    opener = open_conn or _default_open

    conn = opener(db_path)
    ok, msg = check(conn)
    if ok:
        return conn
    logger.error("integrity check failed; attempting restore", extra={"reason": msg})
    conn.close()

    moved = restore_from_snapshot(db_path, backup_dir)
    if moved is None:
        raise DBIntegrityError(
            f"db corrupt and no snapshot available: {msg}"
        )

    conn2 = opener(db_path)
    ok2, msg2 = check(conn2)
    if not ok2:
        conn2.close()
        raise DBIntegrityError(
            f"snapshot also failed integrity_check: {msg2}"
        )
    return conn2


def _default_open(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn
