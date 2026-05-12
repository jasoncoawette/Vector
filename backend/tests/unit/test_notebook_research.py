from __future__ import annotations

from pathlib import Path

import pytest

from vector.memory import HashEmbedder, SqliteMemoryStore
from vector.notebook import NotebookStore
from vector.notebook.research import (
    CITATION_RE,
    RESEARCH_SYSTEM,
    answer,
)
from vector.store import connect
from vector.voice.brain import BrainReply, FakeBrain


@pytest.fixture()
def setup(tmp_path: Path):
    conn = connect(tmp_path / "v.db", check_integrity=False)
    memory = SqliteMemoryStore(conn, HashEmbedder())
    store = NotebookStore(conn, memory)
    yield store, memory, conn
    conn.close()


def _seed(store, name: str) -> None:
    store.create(name)
    store.add_source(
        name,
        handle="afwerx-phase-ii.pdf",
        kind="file",
        text=(
            "AFWERX SBIR Phase II runs for 24 months with up to $1.5M in funding. "
            "Phase II requires a customer-validated dual-use roadmap. "
        )
        * 30,
    )
    store.add_source(
        name,
        handle="https://stratus.dev/roadmap",
        kind="url",
        text=(
            "Stratus Lattice integration ships in Q3 alongside the CLI. "
            "Compute targets focus on Anduril Lattice nodes. "
        )
        * 30,
    )


async def test_research_system_prompt_includes_citation_rule():
    assert "(handle)" in RESEARCH_SYSTEM or "handle" in RESEARCH_SYSTEM.lower()
    assert "ONLY" in RESEARCH_SYSTEM


async def test_empty_query_rejected(setup):
    store, memory, _ = setup
    _seed(store, "research")
    with pytest.raises(ValueError, match="empty query"):
        await answer(
            "",
            notebook="research",
            memory=memory,
            notebook_store=store,
            brain=FakeBrain([]),
        )


async def test_unknown_notebook_rejected(setup):
    store, memory, _ = setup
    with pytest.raises(ValueError, match="unknown notebook"):
        await answer(
            "anything",
            notebook="missing",
            memory=memory,
            notebook_store=store,
            brain=FakeBrain([]),
        )


async def test_empty_notebook_returns_polite_message(setup):
    store, memory, _ = setup
    store.create("empty")
    result = await answer(
        "what's the deal?",
        notebook="empty",
        memory=memory,
        notebook_store=store,
        brain=FakeBrain([]),
    )
    assert "no sources" in result.text.lower()
    assert result.citations == []


async def test_valid_citations_passed_through(setup):
    store, memory, _ = setup
    _seed(store, "research")
    brain = FakeBrain(
        [
            BrainReply(
                text=(
                    "Phase II runs 24 months with up to $1.5M (afwerx-phase-ii.pdf). "
                    "Stratus targets Anduril Lattice nodes (https://stratus.dev/roadmap)."
                ),
                final=True,
                cost_usd=0.001,
            )
        ]
    )
    result = await answer(
        "what does AFWERX Phase II offer?",
        notebook="research",
        memory=memory,
        notebook_store=store,
        brain=brain,
    )
    handles = {c.handle for c in result.citations}
    assert "afwerx-phase-ii.pdf" in handles
    assert "https://stratus.dev/roadmap" in handles
    assert result.cost_usd == pytest.approx(0.001)


async def test_phantom_citations_dropped(setup):
    """Brain hallucinates a handle that isn't in the SOURCES block —
    we drop it silently and log a warning."""
    store, memory, _ = setup
    _seed(store, "research")
    brain = FakeBrain(
        [
            BrainReply(
                text=(
                    "Phase II is great (afwerx-phase-ii.pdf). "
                    "Also (fake-handle-not-in-sources.md) according to nothing."
                ),
                final=True,
            )
        ]
    )
    result = await answer(
        "tell me about phase II",
        notebook="research",
        memory=memory,
        notebook_store=store,
        brain=brain,
    )
    handles = {c.handle for c in result.citations}
    assert "afwerx-phase-ii.pdf" in handles
    assert "fake-handle-not-in-sources.md" not in handles


async def test_citation_pattern_handles_url_with_dots():
    text = "Stratus ships (https://stratus.dev/roadmap)."
    matches = [m.group(1) for m in CITATION_RE.finditer(text)]
    assert "https://stratus.dev/roadmap" in matches


async def test_answer_text_truncated_above_max(setup):
    """Defensive cap on absurdly long brain replies."""
    store, memory, _ = setup
    _seed(store, "research")
    long = "blah " * 5000  # ~25k chars
    brain = FakeBrain([BrainReply(text=long, final=True)])
    result = await answer(
        "x", notebook="research", memory=memory, notebook_store=store, brain=brain
    )
    assert len(result.text) <= 8000


async def test_brain_sees_handles_in_prompt(setup):
    """Capture the prompt to verify the SOURCES block contains the handles."""
    store, memory, _ = setup
    _seed(store, "research")

    saw_prompt = []

    class _CapturingBrain:
        async def plan(self, prompt, history):
            saw_prompt.append(prompt)
            return BrainReply(text="grounded answer (afwerx-phase-ii.pdf).", final=True)

    await answer(
        "phase II details",
        notebook="research",
        memory=memory,
        notebook_store=store,
        brain=_CapturingBrain(),
    )
    body = saw_prompt[0]
    assert "QUERY:" in body
    assert "SOURCES:" in body
    assert "afwerx-phase-ii.pdf" in body


async def test_top_k_clamped(setup):
    store, memory, _ = setup
    _seed(store, "research")

    brain = FakeBrain([BrainReply(text="ok (afwerx-phase-ii.pdf).", final=True)])
    # k > 12 is clamped silently to 12.
    result = await answer(
        "anything",
        notebook="research",
        memory=memory,
        notebook_store=store,
        brain=brain,
        top_k=999,
    )
    # Doesn't crash; returns an answer.
    assert result.text
