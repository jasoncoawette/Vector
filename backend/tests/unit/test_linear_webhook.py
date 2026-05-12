from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from vector.app import app
from vector.config import get_settings
from vector.deps import set_db
from vector.store import connect
from vector.store import tasks as tasks_repo
from vector.webhooks.linear import (
    MAX_PAYLOAD_BYTES,
    handle_linear_event,
    verify_linear_signature,
)

SECRET = "wh-secret"


def _sign(body: bytes, secret: str = SECRET) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


@pytest.fixture()
def client(tmp_path: Path):
    conn = connect(tmp_path / "v.db")
    set_db(conn)
    s = get_settings()
    original = s.linear_webhook_secret
    s.linear_webhook_secret = SECRET
    try:
        yield TestClient(app), conn
    finally:
        s.linear_webhook_secret = original
        set_db(None)
        conn.close()


def _issue_payload(**overrides) -> dict:
    base = {
        "action": "update",
        "type": "Issue",
        "createdAt": "2026-05-12T05:00:00.000Z",
        "data": {
            "id": "lin-issue-1",
            "title": "Ship Stratus CLI",
            "priority": 1,
            "estimate": 5,
            "state": {"name": "In Progress"},
        },
    }
    base.update(overrides)
    return base


def test_signature_valid_dispatches_upsert(client):
    c, conn = client
    body = json.dumps(_issue_payload()).encode()
    r = c.post(
        "/webhooks/linear",
        content=body,
        headers={"Linear-Signature": _sign(body), "content-type": "application/json"},
    )
    assert r.status_code == 200
    assert r.json()["ok"] is True
    open_tasks = tasks_repo.list_open(conn)
    assert any(t.external_id == "lin-issue-1" for t in open_tasks)


def test_missing_signature_returns_401(client):
    c, _ = client
    body = json.dumps(_issue_payload()).encode()
    r = c.post(
        "/webhooks/linear",
        content=body,
        headers={"content-type": "application/json"},
    )
    assert r.status_code == 401


def test_wrong_signature_returns_401(client):
    c, _ = client
    body = json.dumps(_issue_payload()).encode()
    r = c.post(
        "/webhooks/linear",
        content=body,
        headers={"Linear-Signature": "0" * 64, "content-type": "application/json"},
    )
    assert r.status_code == 401


def test_tampered_body_rejected(client):
    c, _ = client
    body = json.dumps(_issue_payload()).encode()
    sig = _sign(body)
    tampered = body.replace(b"Ship Stratus CLI", b"Ship Stolen CLI")
    r = c.post(
        "/webhooks/linear",
        content=tampered,
        headers={"Linear-Signature": sig, "content-type": "application/json"},
    )
    assert r.status_code == 401


def test_non_issue_type_ignored(client):
    c, _ = client
    body = json.dumps(_issue_payload(type="Comment")).encode()
    r = c.post(
        "/webhooks/linear",
        content=body,
        headers={"Linear-Signature": _sign(body), "content-type": "application/json"},
    )
    assert r.status_code == 200
    assert r.json().get("ignored") is True


def test_done_issue_marks_shipped(client):
    c, conn = client
    body = json.dumps(
        _issue_payload(data={
            "id": "lin-issue-2",
            "title": "Old task",
            "priority": 2,
            "estimate": 1,
            "state": {"name": "Done"},
        })
    ).encode()
    r = c.post(
        "/webhooks/linear",
        content=body,
        headers={"Linear-Signature": _sign(body), "content-type": "application/json"},
    )
    assert r.status_code == 200
    open_external = {t.external_id for t in tasks_repo.list_open(conn)}
    assert "lin-issue-2" not in open_external


def test_webhook_not_configured_returns_503(tmp_path: Path):
    conn = connect(tmp_path / "v.db")
    set_db(conn)
    s = get_settings()
    s.linear_webhook_secret = ""
    try:
        c = TestClient(app)
        r = c.post("/webhooks/linear", content=b"{}", headers={"content-type": "application/json"})
        assert r.status_code == 503
    finally:
        set_db(None)
        conn.close()


def test_oversize_payload_rejected():
    huge = b"x" * (MAX_PAYLOAD_BYTES + 1)
    with pytest.raises(ValueError, match="too large"):
        verify_linear_signature(huge, signature="x", secret=SECRET)


def test_missing_secret_rejected():
    with pytest.raises(ValueError, match="not configured"):
        verify_linear_signature(b"{}", signature="x", secret="")


def test_bad_payload_shape_ignored(tmp_path):
    conn = connect(tmp_path / "v.db")
    try:
        out = handle_linear_event(conn, {"action": "update"})
        assert out["ignored"] is True
    finally:
        conn.close()
