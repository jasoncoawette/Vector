from __future__ import annotations

import hashlib
import json
import sqlite3
import struct
import time
from dataclasses import dataclass
from typing import Protocol

DIM = 256


class Embedder(Protocol):
    @property
    def dim(self) -> int: ...
    def embed(self, text: str) -> list[float]: ...


class HashEmbedder:
    """Deterministic local embedder. Good enough for ITAR-safe recall;
    swap for a hosted embedder when content is public."""

    def __init__(self, dim: int = DIM) -> None:
        if dim <= 0:
            raise ValueError("dim must be positive")
        self._dim = dim

    @property
    def dim(self) -> int:
        return self._dim

    def embed(self, text: str) -> list[float]:
        if not text:
            return [0.0] * self._dim
        vec = [0.0] * self._dim
        for token in text.lower().split():
            h = int.from_bytes(hashlib.blake2b(token.encode(), digest_size=8).digest(), "big")
            sign = 1.0 if (h & 1) else -1.0
            vec[(h >> 1) % self._dim] += sign
        norm = sum(v * v for v in vec) ** 0.5
        if norm == 0.0:
            return vec
        return [v / norm for v in vec]


@dataclass
class Memory:
    id: int
    kind: str
    text: str
    meta: dict
    recorded_at: float
    score: float = 0.0


class MemoryStore(Protocol):
    def add(self, kind: str, text: str, meta: dict | None = None) -> int: ...
    def search(self, query: str, *, kind: str | None = None, k: int = 5) -> list[Memory]: ...
    def recent(self, *, kind: str | None = None, limit: int = 20) -> list[Memory]: ...


def _pack(vec: list[float]) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


def _unpack(blob: bytes) -> list[float]:
    n = len(blob) // 4
    return list(struct.unpack(f"{n}f", blob))


def _cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    return dot


class SqliteMemoryStore:
    def __init__(self, conn: sqlite3.Connection, embedder: Embedder) -> None:
        self._conn = conn
        self._embedder = embedder

    def add(self, kind: str, text: str, meta: dict | None = None) -> int:
        if not kind.strip():
            raise ValueError("empty kind")
        if not text.strip():
            raise ValueError("empty text")
        vec = self._embedder.embed(text)
        cur = self._conn.execute(
            "INSERT INTO memories(kind, text, embedding, meta, recorded_at) VALUES(?, ?, ?, ?, ?)",
            (
                kind,
                text,
                _pack(vec),
                json.dumps(meta or {}),
                time.time(),
            ),
        )
        return int(cur.lastrowid)

    def search(self, query: str, *, kind: str | None = None, k: int = 5) -> list[Memory]:
        k = max(1, min(k, 50))
        qvec = self._embedder.embed(query)
        if kind:
            rows = self._conn.execute(
                "SELECT * FROM memories WHERE kind = ?", (kind,)
            ).fetchall()
        else:
            rows = self._conn.execute("SELECT * FROM memories").fetchall()
        scored: list[Memory] = []
        for r in rows:
            score = _cosine(qvec, _unpack(r["embedding"]))
            scored.append(_row(r, score))
        scored.sort(key=lambda m: -m.score)
        return scored[:k]

    def recent(self, *, kind: str | None = None, limit: int = 20) -> list[Memory]:
        limit = max(1, min(limit, 200))
        if kind:
            rows = self._conn.execute(
                "SELECT * FROM memories WHERE kind = ? ORDER BY recorded_at DESC LIMIT ?",
                (kind, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM memories ORDER BY recorded_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [_row(r, 0.0) for r in rows]


def _row(r: sqlite3.Row, score: float) -> Memory:
    return Memory(
        id=r["id"],
        kind=r["kind"],
        text=r["text"],
        meta=json.loads(r["meta"]) if r["meta"] else {},
        recorded_at=r["recorded_at"],
        score=score,
    )
