"""Notebook + Source persistence + chunk indexing into the memory store.

Lazy-created tables (CREATE IF NOT EXISTS at first use) — same pattern
as the Google token store. We delegate the actual vector index to
`memory.SqliteMemoryStore`; the notebook layer only owns the
catalog of (notebook, source) -> (kind, handle) plus chunk membership
so we can find citations and delete sources cleanly.
"""
from __future__ import annotations

import json
import re
import sqlite3
import time
from typing import Iterable

from ..memory import MemoryStore
from .types import Notebook, Source

SCHEMA = """
CREATE TABLE IF NOT EXISTS notebooks (
    name TEXT PRIMARY KEY,
    description TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS notebook_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    notebook TEXT NOT NULL,
    handle TEXT NOT NULL,
    kind TEXT NOT NULL,
    chunks INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL,
    FOREIGN KEY (notebook) REFERENCES notebooks(name),
    UNIQUE(notebook, handle)
);
CREATE TABLE IF NOT EXISTS notebook_chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER NOT NULL,
    memory_id INTEGER NOT NULL,
    ordinal INTEGER NOT NULL,
    FOREIGN KEY (source_id) REFERENCES notebook_sources(id)
);
CREATE INDEX IF NOT EXISTS idx_notebook_chunks_source ON notebook_chunks(source_id);
CREATE INDEX IF NOT EXISTS idx_notebook_chunks_memory ON notebook_chunks(memory_id);
"""

# Notebook chunk sizing. Paragraph-aware: split on double newline, then
# merge until we hit MIN_CHARS, and split anything over MAX_CHARS.
MIN_CHARS = 200
MAX_CHARS = 1200


def chunk_text(text: str) -> list[str]:
    """Split text into chunks. Pure function; testable on its own."""
    if not text or not text.strip():
        return []
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    out: list[str] = []
    buf: list[str] = []
    cur_len = 0
    for p in paragraphs:
        # Hard-split long paragraphs to MAX_CHARS without losing words.
        for sub in _wrap(p, MAX_CHARS):
            if cur_len and cur_len + len(sub) > MAX_CHARS:
                out.append("\n\n".join(buf).strip())
                buf, cur_len = [], 0
            buf.append(sub)
            cur_len += len(sub) + 2
            if cur_len >= MIN_CHARS and cur_len >= MAX_CHARS // 2:
                # Flush at a natural boundary once we're above MIN_CHARS.
                out.append("\n\n".join(buf).strip())
                buf, cur_len = [], 0
    if buf:
        out.append("\n\n".join(buf).strip())
    return out


def _wrap(s: str, n: int) -> list[str]:
    """Split a long string into <=n character pieces, preferring word
    boundaries when possible."""
    if len(s) <= n:
        return [s]
    out = []
    while len(s) > n:
        # Find a space near the limit.
        cut = s.rfind(" ", 0, n)
        if cut < n // 2:
            cut = n  # no good break — hard cut
        out.append(s[:cut].rstrip())
        s = s[cut:].lstrip()
    if s:
        out.append(s)
    return out


class NotebookStore:
    def __init__(self, conn: sqlite3.Connection, memory: MemoryStore) -> None:
        self._conn = conn
        self._memory = memory
        conn.executescript(SCHEMA)

    # --- notebooks --------------------------------------------------

    def create(self, name: str, description: str = "") -> None:
        name = name.strip()
        if not name:
            raise ValueError("empty notebook name")
        self._conn.execute(
            "INSERT INTO notebooks(name, description, created_at) VALUES(?, ?, ?) "
            "ON CONFLICT(name) DO UPDATE SET description=excluded.description",
            (name, description, time.time()),
        )

    def list_notebooks(self) -> list[Notebook]:
        rows = self._conn.execute(
            "SELECT name, description FROM notebooks ORDER BY name"
        ).fetchall()
        out: list[Notebook] = []
        for r in rows:
            srcs = self._sources(r["name"])
            out.append(
                Notebook(
                    name=r["name"],
                    description=r["description"],
                    sources=srcs,
                    chunks=sum(s.chunks for s in srcs),
                )
            )
        return out

    def get(self, name: str) -> Notebook | None:
        row = self._conn.execute(
            "SELECT name, description FROM notebooks WHERE name=?", (name,)
        ).fetchone()
        if row is None:
            return None
        srcs = self._sources(name)
        return Notebook(
            name=row["name"],
            description=row["description"],
            sources=srcs,
            chunks=sum(s.chunks for s in srcs),
        )

    def delete(self, name: str) -> bool:
        """Drop the notebook and every source/chunk under it. Memory
        rows are deleted by id, not by name pattern, so a chunk that
        happens to share a memory kind with another notebook stays put."""
        srcs = self._sources(name)
        for s in srcs:
            self.remove_source(s.id)
        cur = self._conn.execute("DELETE FROM notebooks WHERE name=?", (name,))
        return cur.rowcount > 0

    # --- sources ----------------------------------------------------

    def add_source(
        self,
        notebook: str,
        *,
        handle: str,
        kind: str,
        text: str,
    ) -> Source:
        """Chunk `text`, embed each chunk into memory under
        kind=f"notebook:{notebook}", and record the membership."""
        if self.get(notebook) is None:
            raise ValueError(f"unknown notebook: {notebook}")
        chunks = chunk_text(text)
        if not chunks:
            raise ValueError("source has no usable text")
        now = time.time()
        cur = self._conn.execute(
            "INSERT INTO notebook_sources(notebook, handle, kind, chunks, created_at) "
            "VALUES(?, ?, ?, ?, ?) ON CONFLICT(notebook, handle) DO UPDATE SET "
            "kind=excluded.kind, chunks=excluded.chunks, created_at=excluded.created_at",
            (notebook, handle, kind, len(chunks), now),
        )
        # ON CONFLICT doesn't return a lastrowid when it updated — look up the row.
        sid_row = self._conn.execute(
            "SELECT id FROM notebook_sources WHERE notebook=? AND handle=?",
            (notebook, handle),
        ).fetchone()
        source_id = int(sid_row["id"])
        # If this was an update (re-add), drop the old chunks first.
        self._conn.execute(
            "DELETE FROM notebook_chunks WHERE source_id=?", (source_id,)
        )
        memory_kind = f"notebook:{notebook}"
        for ordinal, chunk in enumerate(chunks):
            memory_id = self._memory.add(
                memory_kind,
                chunk,
                meta={"handle": handle, "kind": kind, "ordinal": ordinal},
            )
            self._conn.execute(
                "INSERT INTO notebook_chunks(source_id, memory_id, ordinal) "
                "VALUES(?, ?, ?)",
                (source_id, memory_id, ordinal),
            )
        return Source(
            id=source_id,
            notebook=notebook,
            handle=handle,
            kind=kind,
            chunks=len(chunks),
            created_at=now,
        )

    def remove_source(self, source_id: int) -> bool:
        rows = self._conn.execute(
            "SELECT memory_id FROM notebook_chunks WHERE source_id=?", (source_id,)
        ).fetchall()
        for r in rows:
            self._conn.execute("DELETE FROM memories WHERE id=?", (r["memory_id"],))
        self._conn.execute("DELETE FROM notebook_chunks WHERE source_id=?", (source_id,))
        cur = self._conn.execute(
            "DELETE FROM notebook_sources WHERE id=?", (source_id,)
        )
        return cur.rowcount > 0

    def chunks_for_handle(self, notebook: str, handle: str) -> Iterable[tuple[int, str]]:
        """Yield (memory_id, snippet_text) tuples — used at recall time
        to look up the original text behind a memory hit."""
        rows = self._conn.execute(
            """
            SELECT nc.memory_id, m.text
            FROM notebook_chunks nc
            JOIN notebook_sources ns ON ns.id = nc.source_id
            JOIN memories m ON m.id = nc.memory_id
            WHERE ns.notebook=? AND ns.handle=?
            ORDER BY nc.ordinal
            """,
            (notebook, handle),
        ).fetchall()
        for r in rows:
            yield int(r["memory_id"]), r["text"]

    def source_for_memory(self, memory_id: int) -> Source | None:
        row = self._conn.execute(
            """
            SELECT ns.id, ns.notebook, ns.handle, ns.kind, ns.chunks, ns.created_at
            FROM notebook_chunks nc
            JOIN notebook_sources ns ON ns.id = nc.source_id
            WHERE nc.memory_id=?
            """,
            (memory_id,),
        ).fetchone()
        if row is None:
            return None
        return Source(
            id=row["id"],
            notebook=row["notebook"],
            handle=row["handle"],
            kind=row["kind"],
            chunks=row["chunks"],
            created_at=row["created_at"],
        )

    # --- internal ---------------------------------------------------

    def _sources(self, notebook: str) -> list[Source]:
        rows = self._conn.execute(
            "SELECT id, notebook, handle, kind, chunks, created_at "
            "FROM notebook_sources WHERE notebook=? ORDER BY created_at",
            (notebook,),
        ).fetchall()
        return [
            Source(
                id=r["id"],
                notebook=r["notebook"],
                handle=r["handle"],
                kind=r["kind"],
                chunks=r["chunks"],
                created_at=r["created_at"],
            )
            for r in rows
        ]
