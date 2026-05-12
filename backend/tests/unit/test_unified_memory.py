from __future__ import annotations

from pathlib import Path

import pytest

from vector.memory import HashEmbedder, SqliteMemoryStore
from vector.store import connect
from vector.tools.builder import build_registry_for
from vector.tools.errors import ToolDenied
from vector.tools.files import FileGuard


@pytest.fixture()
def setup(tmp_path: Path):
    conn = connect(tmp_path / "v.db")
    memory = SqliteMemoryStore(conn, HashEmbedder())
    read_root = tmp_path / "home"
    read_root.mkdir()
    guard = FileGuard(read_root=read_root, write_root=read_root / "ws")
    yield {"conn": conn, "memory": memory, "guard": guard}
    conn.close()


def test_research_agent_gets_search_and_add(setup):
    reg = build_registry_for("research", guard=setup["guard"], memory=setup["memory"])
    names = {t["name"] for t in reg.list()}
    assert "memory.search" in names
    assert "memory.add" in names


def test_writer_agent_gets_both(setup):
    reg = build_registry_for("writer", guard=setup["guard"], memory=setup["memory"])
    names = {t["name"] for t in reg.list()}
    assert "memory.search" in names
    assert "memory.add" in names


def test_code_agent_search_only(setup):
    reg = build_registry_for("code", guard=setup["guard"], memory=setup["memory"])
    names = {t["name"] for t in reg.list()}
    assert "memory.search" in names
    assert "memory.add" not in names


def test_tester_agent_search_only(setup):
    reg = build_registry_for("tester", guard=setup["guard"], memory=setup["memory"])
    names = {t["name"] for t in reg.list()}
    assert "memory.search" in names
    assert "memory.add" not in names


def test_security_agent_gets_both(setup):
    reg = build_registry_for("security", guard=setup["guard"], memory=setup["memory"])
    names = {t["name"] for t in reg.list()}
    assert "memory.search" in names
    assert "memory.add" in names


def test_no_memory_means_no_memory_tools(setup):
    reg = build_registry_for("research", guard=setup["guard"], memory=None)
    names = {t["name"] for t in reg.list()}
    assert "memory.search" not in names
    assert "memory.add" not in names


def test_memory_search_via_registry_returns_hits(setup):
    setup["memory"].add("note", "Anduril Lattice integration plan")
    setup["memory"].add("note", "grocery list")
    reg = build_registry_for("research", guard=setup["guard"], memory=setup["memory"])
    hits = reg.call("memory.search", {"query": "Lattice", "k": 2})
    assert hits[0]["text"].startswith("Anduril")


def test_memory_add_via_registry_persists(setup):
    reg = build_registry_for("writer", guard=setup["guard"], memory=setup["memory"])
    out = reg.call("memory.add", {"kind": "draft", "text": "first paragraph"})
    assert "id" in out
    recent = setup["memory"].recent(kind="draft")
    assert recent[0].text == "first paragraph"


def test_code_agent_cannot_call_memory_add(setup):
    reg = build_registry_for("code", guard=setup["guard"], memory=setup["memory"])
    with pytest.raises(ToolDenied, match="unknown tool"):
        reg.call("memory.add", {"kind": "x", "text": "y"})


def test_memory_search_args_bounded(setup):
    reg = build_registry_for("research", guard=setup["guard"], memory=setup["memory"])
    with pytest.raises(ToolDenied):
        reg.call("memory.search", {"query": "", "k": 5})
    with pytest.raises(ToolDenied):
        reg.call("memory.search", {"query": "x", "k": 999})


def test_executor_routes_to_per_agent_registry(setup):
    from vector.agents.executor import ClaudeAgentExecutor
    from vector.agents.types import AgentSpec
    from vector.voice.brain import BrainReply, FakeBrain

    setup["memory"].add("style", "short sentences. no filler.")

    def regf(agent_type: str):
        return build_registry_for(agent_type, guard=setup["guard"], memory=setup["memory"])

    def factory(_t: str, *, prompt: str | None = None):
        return FakeBrain(
            [
                BrainReply(
                    tool_call={"name": "memory.search", "args": {"query": "style", "k": 1}},
                    final=False,
                    cost_usd=0.0,
                ),
                BrainReply(text="ok", final=True, cost_usd=0.0),
            ]
        )

    ex = ClaudeAgentExecutor(brain_factory=factory, registry_factory=regf)
    import asyncio

    result = asyncio.run(ex(AgentSpec(type="writer", prompt="draft"), "draft"))
    assert result.output == "ok"
