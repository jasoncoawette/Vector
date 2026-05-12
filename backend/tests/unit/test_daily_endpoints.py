from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from vector.app import app
from vector.deps import set_db
from vector.store import connect


@pytest.fixture()
def client(tmp_path: Path):
    conn = connect(tmp_path / "v.db")
    set_db(conn)
    c = TestClient(app)
    yield c, conn
    set_db(None)
    conn.close()


def _seed_task(c: TestClient, **kw):
    body = {"title": "t", "source": "linear", "tag": "outcome", "mission": "stratus"}
    body.update(kw)
    r = c.post("/tasks", json=body)
    return r.json()["id"]


def test_metric_post_then_get(client):
    c, _ = client
    r = c.post(
        "/metrics",
        json={"section": "stratus", "name": "revenue", "value": 1000, "unit": "usd"},
    )
    assert r.status_code == 200
    r = c.get("/metrics?section=stratus")
    body = r.json()
    assert body["sections"]["stratus"][0]["name"] == "revenue"


def test_metric_rejects_unknown_section(client):
    c, _ = client
    r = c.post("/metrics", json={"section": "boeing", "name": "x", "value": 1})
    assert r.status_code == 400


def test_picks_endpoint_returns_three(client):
    c, _ = client
    for i in range(5):
        _seed_task(c, external_id=f"T{i}", title=f"task {i}", priority=i + 1)
    r = c.get("/daily/picks?day=2026-05-12")
    assert r.status_code == 200
    assert len(r.json()["picks"]) == 3


def test_brief_endpoint_returns_text(client):
    c, _ = client
    for i in range(3):
        _seed_task(c, external_id=f"T{i}", title=f"task {i}", priority=1)
    r = c.get("/daily/brief")
    assert r.status_code == 200
    assert "Jason" in r.json()["text"]


def test_override_shifts_weights(client):
    c, _ = client
    a = _seed_task(c, external_id="A", title="A", tag="process", priority=3)
    b = _seed_task(c, external_id="B", title="B", tag="outcome", priority=2)
    r = c.post(
        "/daily/override",
        json={"day": "2026-05-12", "removed_task_id": a, "added_task_id": b},
    )
    assert r.status_code == 200
    assert r.json()["weights"]["outcome"] > 1.0


def test_review_endpoint_marks_shipped(client):
    c, conn = client
    a = _seed_task(c, external_id="A", title="A", priority=1)
    c.get("/daily/picks?day=2026-05-12")
    r = c.post(
        "/daily/review",
        json={"day": "2026-05-12", "shipped_ids": [a], "note": "good day"},
    )
    body = r.json()
    assert a in body["shipped_ids"]
    assert "A" in body["spoken"]
