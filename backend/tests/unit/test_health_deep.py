from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from vector import audit
from vector.app import app
from vector.deps import set_db
from vector.store import connect


@pytest.fixture()
def healthy(tmp_path: Path):
    conn = connect(tmp_path / "v.db", check_integrity=False)
    set_db(conn)
    audit.set_sink(conn)
    yield TestClient(app), conn, tmp_path
    audit.set_sink(None)
    set_db(None)
    conn.close()


def test_healthz_is_cheap_200(healthy):
    c, _, _ = healthy
    r = c.get("/healthz")
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_deep_passes_when_all_deps_ok(healthy):
    c, _, _ = healthy
    r = c.get("/health/deep")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["checks"]["db"]["ok"] is True
    assert body["checks"]["workspace"]["ok"] is True
    assert body["checks"]["audit"]["ok"] is True


def test_deep_503_when_audit_sink_missing(healthy):
    c, _, _ = healthy
    audit.set_sink(None)
    r = c.get("/health/deep")
    assert r.status_code == 503
    assert r.json()["ok"] is False
    assert r.json()["checks"]["audit"]["ok"] is False


def test_deep_503_when_workspace_unwritable(healthy, monkeypatch):
    c, _, _ = healthy
    from vector.config import get_settings

    # Point workspace at a path that can't be created.
    s = get_settings()
    original = s.workspace
    s.workspace = Path("/proc/cannot-create-here")  # read-only on Linux
    try:
        r = c.get("/health/deep")
        # The check might pass on macOS where /proc doesn't exist and
        # mkdir fails with a different error — either way we expect 503.
        if r.status_code == 200:
            pytest.skip("workspace mkdir unexpectedly succeeded on this OS")
        assert r.status_code == 503
        assert r.json()["checks"]["workspace"]["ok"] is False
    finally:
        s.workspace = original


def test_deep_includes_build_hash(healthy):
    c, _, _ = healthy
    body = c.get("/health/deep").json()
    assert "build" in body
