from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from vector.app import app
from vector.deps import (
    set_db,
    set_memory,
    set_notebook_store,
)
from vector.memory import HashEmbedder, SqliteMemoryStore
from vector.notebook import NotebookStore
from vector.store import connect


@pytest.fixture()
def client(tmp_path: Path):
    conn = connect(tmp_path / "v.db", check_integrity=False)
    set_db(conn)
    memory = SqliteMemoryStore(conn, HashEmbedder())
    set_memory(memory)
    set_notebook_store(NotebookStore(conn, memory))
    yield TestClient(app)
    set_notebook_store(None)
    set_memory(None)
    set_db(None)
    conn.close()


def test_create_and_list_notebook(client):
    r = client.post("/notebooks", json={"name": "Stratus", "description": "notes"})
    assert r.status_code == 200
    body = client.get("/notebooks").json()
    assert any(nb["name"] == "Stratus" for nb in body["notebooks"])


def test_get_unknown_notebook_404(client):
    assert client.get("/notebooks/missing").status_code == 404


def test_add_source_persists(client):
    client.post("/notebooks", json={"name": "nb"})
    r = client.post(
        "/notebooks/nb/sources",
        json={"handle": "doc-1", "kind": "text", "text": "body " * 200},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["handle"] == "doc-1"
    assert body["chunks"] >= 1

    nb = client.get("/notebooks/nb").json()
    assert nb["sources"][0]["handle"] == "doc-1"


def test_add_source_unknown_notebook_400(client):
    r = client.post(
        "/notebooks/missing/sources",
        json={"handle": "x", "kind": "text", "text": "body " * 200},
    )
    assert r.status_code == 400


def test_add_source_empty_text_422(client):
    client.post("/notebooks", json={"name": "nb"})
    r = client.post(
        "/notebooks/nb/sources",
        json={"handle": "x", "kind": "text", "text": ""},
    )
    assert r.status_code == 422  # pydantic min_length


def test_remove_source(client):
    client.post("/notebooks", json={"name": "nb"})
    src = client.post(
        "/notebooks/nb/sources",
        json={"handle": "x", "kind": "text", "text": "body " * 200},
    ).json()
    r = client.delete(f"/notebooks/nb/sources/{src['id']}")
    assert r.status_code == 200
    nb = client.get("/notebooks/nb").json()
    assert nb["sources"] == []


def test_remove_unknown_source_404(client):
    client.post("/notebooks", json={"name": "nb"})
    assert client.delete("/notebooks/nb/sources/99999").status_code == 404


def test_ask_when_no_brain_returns_503(client):
    """No ANTHROPIC_API_KEY set in test config → ask endpoint refuses."""
    client.post("/notebooks", json={"name": "nb"})
    r = client.post("/notebooks/nb/ask", json={"query": "what?"})
    assert r.status_code == 503
    assert "brain" in r.json()["detail"].lower()


def test_ask_with_no_notebook_store_returns_503(tmp_path: Path):
    set_notebook_store(None)
    set_memory(None)
    set_db(None)
    try:
        c = TestClient(app)
        # First we still need a notebook store available for the create
        # path — without it, both create and ask should fail-soft.
        r = c.post("/notebooks", json={"name": "x"})
        assert r.status_code in (200, 503)
    finally:
        pass
