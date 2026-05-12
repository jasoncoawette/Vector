"""Notebook = named corpus of sources Vector can answer grounded
questions against. The NotebookLM-shape feature without the scraping.

A `Source` is a chunk of text with a citation handle (a URL, a file
path, or an Obsidian note title). Adding a source means: text is
chunked (by paragraph, capped), each chunk is embedded into the
existing memory store under kind=f"notebook:{name}", and the source
is recorded in `notebook_sources` so we can list / delete it later.

Querying a notebook does a vector search restricted to that notebook's
kind, plus a brain plan() with system=NOTEBOOK_RESEARCH_SYSTEM and a
prompt that includes the top-k chunks. The answer is parsed for
inline citations matching the chunks we sent.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Source:
    id: int
    notebook: str
    handle: str   # the user-facing citation: URL / path / Note title
    kind: str     # "url" | "file" | "obsidian" | "text"
    chunks: int
    created_at: float


@dataclass
class Notebook:
    name: str
    description: str
    sources: list[Source] = field(default_factory=list)
    chunks: int = 0


@dataclass
class Citation:
    source_id: int
    handle: str
    snippet: str


@dataclass
class NotebookAnswer:
    text: str
    citations: list[Citation]
    cost_usd: float = 0.0
