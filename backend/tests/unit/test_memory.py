from __future__ import annotations

from pathlib import Path

import pytest

from vector.memory import HashEmbedder, SqliteMemoryStore
from vector.store import connect


@pytest.fixture()
def store(tmp_path: Path):
    conn = connect(tmp_path / "v.db")
    yield SqliteMemoryStore(conn, HashEmbedder())
    conn.close()


def test_add_and_recent(store):
    a = store.add("task", "ship the CLI")
    b = store.add("task", "draft pitch deck")
    rows = store.recent()
    ids = [m.id for m in rows]
    assert ids == [b, a]


def test_search_ranks_by_similarity(store):
    store.add("note", "Anduril Lattice integration")
    store.add("note", "grocery list")
    store.add("note", "Lattice link spec")
    hits = store.search("Lattice link", k=2)
    assert len(hits) == 2
    assert "Lattice" in hits[0].text
    assert hits[0].score >= hits[1].score


def test_search_filters_by_kind(store):
    store.add("task", "ship CLI")
    store.add("idea", "agent that drafts emails")
    hits = store.search("ship", kind="task")
    assert all(m.kind == "task" for m in hits)


def test_empty_inputs_rejected(store):
    with pytest.raises(ValueError):
        store.add("", "x")
    with pytest.raises(ValueError):
        store.add("task", "  ")


def test_embedder_dim_positive():
    with pytest.raises(ValueError):
        HashEmbedder(dim=0)


def test_search_k_is_clamped(store):
    for i in range(5):
        store.add("task", f"item {i}")
    out = store.search("item", k=999)
    assert len(out) <= 50


def test_recent_limit_is_clamped(store):
    store.add("task", "one")
    out = store.recent(limit=999999)
    assert len(out) <= 200


def test_embedder_is_deterministic():
    e = HashEmbedder()
    assert e.embed("hello world") == e.embed("hello world")


def test_empty_text_embedding_is_zero():
    e = HashEmbedder()
    assert all(v == 0.0 for v in e.embed(""))
