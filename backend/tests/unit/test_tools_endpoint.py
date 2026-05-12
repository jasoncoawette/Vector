from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from vector.app import app, set_registry
from vector.tools.builder import build_default_registry
from vector.tools.files import FileGuard


@pytest.fixture()
def client(tmp_path: Path):
    read_root = tmp_path / "home"
    read_root.mkdir()
    guard = FileGuard(read_root=read_root, write_root=read_root / "workspace")
    set_registry(build_default_registry(guard))
    yield TestClient(app), guard
    set_registry(None)


def test_lists_tools(client):
    c, _ = client
    r = c.get("/tools")
    assert r.status_code == 200
    names = {t["name"] for t in r.json()["tools"]}
    assert {"file.read", "file.write", "file.delete"} <= names


def test_call_file_write_and_read(client):
    c, guard = client
    target = guard.write_root / "note.md"
    w = c.post(
        "/tools/call",
        json={"name": "file.write", "args": {"path": str(target), "content": "hi"}},
    )
    assert w.status_code == 200, w.text
    assert w.json()["ok"] is True

    r = c.post("/tools/call", json={"name": "file.read", "args": {"path": str(target)}})
    assert r.json()["result"]["text"] == "hi"


def test_unknown_tool_returns_403(client):
    c, _ = client
    r = c.post("/tools/call", json={"name": "nope", "args": {}})
    assert r.status_code == 403


def test_outside_scope_returns_403(client, tmp_path):
    c, _ = client
    r = c.post(
        "/tools/call",
        json={"name": "file.read", "args": {"path": str(tmp_path / "outside.txt")}},
    )
    assert r.status_code == 403


def test_delete_two_step_via_http(client):
    c, guard = client
    target = guard.write_root / "kill.txt"
    target.write_text("doomed")
    first = c.post(
        "/tools/call",
        json={"name": "file.delete", "args": {"path": str(target)}},
    )
    body = first.json()
    assert first.status_code == 200
    assert body["ok"] is False
    assert body["needs_confirm"] is True
    token = body["token"]

    second = c.post(
        "/tools/call",
        json={
            "name": "file.delete",
            "args": {"path": str(target), "confirm_token": token},
        },
    )
    assert second.status_code == 200
    assert second.json()["result"]["deleted"] is True
    assert not target.exists()
