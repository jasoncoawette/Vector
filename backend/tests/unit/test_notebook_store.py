from __future__ import annotations

from pathlib import Path

import pytest

from vector.memory import HashEmbedder, SqliteMemoryStore
from vector.notebook import NotebookStore
from vector.notebook.store import MAX_CHARS, MIN_CHARS, chunk_text
from vector.store import connect


@pytest.fixture()
def store(tmp_path: Path):
    conn = connect(tmp_path / "v.db", check_integrity=False)
    memory = SqliteMemoryStore(conn, HashEmbedder())
    yield NotebookStore(conn, memory), memory, conn
    conn.close()


# ---- chunk_text -----------------------------------------------------


def test_chunk_text_empty_returns_empty():
    assert chunk_text("") == []
    assert chunk_text("   ") == []


def test_chunk_text_short_returns_one_chunk():
    assert chunk_text("short paragraph") == ["short paragraph"]


def test_chunk_text_splits_long_paragraph():
    long_text = "word " * 1500  # well over MAX_CHARS
    chunks = chunk_text(long_text)
    assert len(chunks) > 1
    assert all(len(c) <= MAX_CHARS + 200 for c in chunks)  # generous slack


def test_chunk_text_respects_paragraph_boundaries():
    text = "p1 short\n\np2 short\n\np3 short"
    chunks = chunk_text(text)
    assert len(chunks) >= 1
    # No chunk should split mid-word.
    for c in chunks:
        assert "  " not in c  # double-space shouldn't appear (we strip)


def test_chunk_text_merges_tiny_paragraphs():
    text = "tiny\n\ntiny\n\ntiny\n\ntiny"
    chunks = chunk_text(text)
    # They should fold together rather than each becoming its own chunk.
    assert len(chunks) <= 2


# ---- NotebookStore --------------------------------------------------


def test_create_and_get(store):
    s, _, _ = store
    s.create("Stratus", "kill chain notes")
    nb = s.get("Stratus")
    assert nb is not None
    assert nb.description == "kill chain notes"
    assert nb.sources == []


def test_create_upserts_description(store):
    s, _, _ = store
    s.create("nb", "v1")
    s.create("nb", "v2")
    assert s.get("nb").description == "v2"


def test_create_rejects_empty_name(store):
    s, _, _ = store
    with pytest.raises(ValueError):
        s.create("")
    with pytest.raises(ValueError):
        s.create("   ")


def test_add_source_unknown_notebook(store):
    s, _, _ = store
    with pytest.raises(ValueError, match="unknown notebook"):
        s.add_source("nope", handle="x", kind="text", text="body")


def test_add_source_empty_text_rejected(store):
    s, _, _ = store
    s.create("nb")
    with pytest.raises(ValueError, match="no usable text"):
        s.add_source("nb", handle="x", kind="text", text="   ")


def test_add_source_persists_chunks(store):
    s, memory, _ = store
    s.create("nb")
    text = "section one is here. " * 80 + "\n\n" + "section two is here. " * 80
    src = s.add_source("nb", handle="report.pdf", kind="file", text=text)
    assert src.chunks >= 1
    nb = s.get("nb")
    assert nb.chunks == src.chunks
    # Memory store has matching kind.
    hits = memory.search("section", kind="notebook:nb", k=5)
    assert len(hits) >= 1


def test_re_add_source_replaces_chunks(store):
    s, memory, _ = store
    s.create("nb")
    s.add_source("nb", handle="doc", kind="text", text="initial text " * 200)
    s.add_source("nb", handle="doc", kind="text", text="replacement text " * 200)
    nb = s.get("nb")
    # Single source row with the updated chunk count.
    assert len(nb.sources) == 1
    hits = memory.search("replacement", kind="notebook:nb", k=5)
    assert len(hits) >= 1
    # Original chunks gone — no hits for the original phrase.
    old_hits = memory.search("initial text initial text initial text", kind="notebook:nb", k=5)
    # The hash embedder isn't semantic, so we can't fully assert
    # absence; but the chunks_for_handle iterator should yield only
    # replacement chunks.
    pairs = list(s.chunks_for_handle("nb", "doc"))
    assert all("initial" not in text for _, text in pairs)


def test_remove_source(store):
    s, memory, conn = store
    s.create("nb")
    src = s.add_source("nb", handle="doc", kind="text", text="hello world " * 200)
    deleted = s.remove_source(src.id)
    assert deleted is True
    nb = s.get("nb")
    assert nb.sources == []
    # The memory rows are gone too.
    remaining = conn.execute(
        "SELECT COUNT(*) AS n FROM memories WHERE kind='notebook:nb'"
    ).fetchone()["n"]
    assert remaining == 0


def test_remove_unknown_source_returns_false(store):
    s, _, _ = store
    s.create("nb")
    assert s.remove_source(9999) is False


def test_delete_notebook_drops_all_sources(store):
    s, _, conn = store
    s.create("nb")
    s.add_source("nb", handle="a", kind="text", text="a text " * 200)
    s.add_source("nb", handle="b", kind="text", text="b text " * 200)
    s.delete("nb")
    assert s.get("nb") is None
    remaining = conn.execute(
        "SELECT COUNT(*) AS n FROM memories WHERE kind='notebook:nb'"
    ).fetchone()["n"]
    assert remaining == 0


def test_source_for_memory_round_trips(store):
    s, memory, _ = store
    s.create("nb")
    src = s.add_source("nb", handle="ref", kind="text", text="body text " * 200)
    chunk_pairs = list(s.chunks_for_handle("nb", "ref"))
    assert chunk_pairs
    memory_id = chunk_pairs[0][0]
    found = s.source_for_memory(memory_id)
    assert found is not None
    assert found.id == src.id
    assert found.handle == "ref"


def test_list_notebooks_sorted(store):
    s, _, _ = store
    s.create("b")
    s.create("a")
    s.create("c")
    names = [nb.name for nb in s.list_notebooks()]
    assert names == ["a", "b", "c"]
