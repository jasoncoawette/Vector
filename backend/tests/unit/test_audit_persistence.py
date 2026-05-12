from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from vector import audit
from vector.app import app
from vector.deps import set_db
from vector.store import connect


@pytest.fixture()
def client(tmp_path: Path):
    conn = connect(tmp_path / "v.db")
    set_db(conn)
    audit.set_sink(conn)
    c = TestClient(app)
    yield c, conn
    audit.set_sink(None)
    set_db(None)
    conn.close()


def test_record_writes_to_sqlite(client):
    _, conn = client
    audit.record("file.read", "brain", {"path": "/x"}, {"text": "hi"}, ok=True)
    n = conn.execute("SELECT COUNT(*) AS n FROM audit_log").fetchone()["n"]
    assert n == 1


def test_tail_returns_newest_first(client):
    _, conn = client
    audit.record("a", "u", {}, {}, ok=True)
    audit.record("b", "u", {}, {}, ok=False)
    entries = audit.tail(conn, limit=10)
    assert entries[0]["tool"] == "b"
    assert entries[1]["tool"] == "a"


def test_audit_endpoint(client):
    c, _ = client
    audit.record("x", "user", {}, {}, ok=True)
    r = c.get("/audit?limit=5")
    assert r.status_code == 200
    body = r.json()
    assert body["entries"][0]["tool"] == "x"


def test_args_never_persisted_only_hash(client):
    _, conn = client
    audit.record("file.read", "u", {"path": "/etc/passwd"}, {"text": "ok"}, ok=True)
    row = conn.execute("SELECT * FROM audit_log").fetchone()
    assert "/etc/passwd" not in str(dict(row))


def test_tool_call_endpoint_persists_audit(client):
    c, conn = client
    from vector.app import set_registry
    from vector.tools.builder import build_default_registry
    from vector.tools.files import FileGuard

    read_root = Path(conn.execute("PRAGMA database_list").fetchone()["file"]).parent
    guard = FileGuard(read_root=read_root, write_root=read_root / "workspace")
    set_registry(build_default_registry(guard))
    try:
        c.post(
            "/tools/call",
            json={
                "name": "file.write",
                "args": {"path": str(guard.write_root / "x.txt"), "content": "hi"},
            },
        )
        rows = audit.tail(conn, limit=10)
        assert any(e["tool"] == "file.write" for e in rows)
    finally:
        set_registry(None)
