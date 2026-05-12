"""Grounded research against a notebook.

Flow:
  1. memory.search(query, kind="notebook:<name>", k=top_k) -> chunk hits
  2. Build a prompt that interleaves each chunk with a `(handle)` tag
  3. brain.plan(prompt) -> answer text with inline `(handle)` citations
  4. Parse citations back into Citation objects for the response payload

We don't trust the brain to invent handles. The citation parser only
accepts handles that appeared in the prompt; anything else gets dropped
with a "phantom_citation" log line so the brain's hallucinations don't
leak into the audit trail.
"""
from __future__ import annotations

import logging
import re
from typing import Awaitable, Callable

from ..memory import MemoryStore
from ..prompts import compose, CITATION_RULE, NO_HALLUCINATION_RULE
from ..voice.brain import Brain
from .store import NotebookStore
from .types import Citation, NotebookAnswer

logger = logging.getLogger("vector.notebook.research")

DEFAULT_TOP_K = 6
MAX_QUERY_CHARS = 1000
MAX_ANSWER_CHARS = 8000

RESEARCH_SYSTEM = compose(
    "You are Vector's grounded research assistant. You will be given a "
    "QUERY and a set of SOURCES, each tagged with a handle. Answer the "
    "query using ONLY information present in the SOURCES.",
    "Cite every claim inline as `(handle)` right after the sentence it "
    "supports. Citations must use one of the handles provided. Never "
    "invent a handle. If the sources don't cover the question, say so "
    "in one sentence — don't pad with general knowledge.",
    NO_HALLUCINATION_RULE,
    CITATION_RULE,
)

# Citation pattern: `(handle)` where handle is non-empty and doesn't
# contain a newline or paren. Letters / digits / common punctuation only.
CITATION_RE = re.compile(r"\(([^\n()]{2,200})\)")


async def answer(
    query: str,
    *,
    notebook: str,
    memory: MemoryStore,
    notebook_store: NotebookStore,
    brain: Brain,
    top_k: int = DEFAULT_TOP_K,
) -> NotebookAnswer:
    """Run a grounded research turn against `notebook`.

    `brain` is the LLM that produces the answer; we typically wire this
    to ClaudeBrain with system=RESEARCH_SYSTEM. The caller controls
    which tier so the cost is predictable."""
    query = (query or "").strip()
    if not query:
        raise ValueError("empty query")
    if len(query) > MAX_QUERY_CHARS:
        query = query[:MAX_QUERY_CHARS]

    nb = notebook_store.get(notebook)
    if nb is None:
        raise ValueError(f"unknown notebook: {notebook}")
    if nb.chunks == 0:
        return NotebookAnswer(
            text="This notebook has no sources yet — add some before asking.",
            citations=[],
        )

    top_k = max(1, min(top_k, 12))
    hits = memory.search(query, kind=f"notebook:{notebook}", k=top_k)
    if not hits:
        return NotebookAnswer(
            text="No matching passages in this notebook.",
            citations=[],
        )

    # Map memory_id -> source so we can find handles after the brain replies.
    by_memory: dict[int, tuple[str, str]] = {}
    sources_block: list[str] = []
    for h in hits:
        src = notebook_store.source_for_memory(h.id)
        if src is None:
            # Stale memory row; skip.
            continue
        by_memory[h.id] = (src.handle, h.text)
        sources_block.append(
            f"--- SOURCE (memory_id={h.id}) (handle={src.handle}) ---\n{h.text}"
        )
    if not sources_block:
        return NotebookAnswer(
            text="Sources found but no matching catalog entry — re-add and retry.",
            citations=[],
        )

    prompt = (
        f"QUERY:\n{query}\n\n"
        f"SOURCES:\n" + "\n\n".join(sources_block) + "\n\n"
        "Answer the query using ONLY the SOURCES above. Cite every "
        "claim with `(handle)` immediately after the supporting "
        "sentence, using one of the handles shown above."
    )

    reply = await brain.plan(prompt, history=[])
    text = (reply.text or "").strip()
    if len(text) > MAX_ANSWER_CHARS:
        text = text[:MAX_ANSWER_CHARS]

    valid_handles = {handle for handle, _ in by_memory.values()}
    citations: list[Citation] = []
    seen_pairs: set[tuple[int, str]] = set()
    for m in CITATION_RE.finditer(text):
        handle = m.group(1).strip()
        if handle not in valid_handles:
            logger.warning("phantom_citation %r", handle)
            continue
        # Find a memory_id that backs this handle.
        for mem_id, (h, snippet) in by_memory.items():
            if h == handle and (mem_id, handle) not in seen_pairs:
                citations.append(
                    Citation(
                        source_id=mem_id,
                        handle=handle,
                        snippet=snippet[:200],
                    )
                )
                seen_pairs.add((mem_id, handle))
                break

    return NotebookAnswer(text=text, citations=citations, cost_usd=reply.cost_usd)
