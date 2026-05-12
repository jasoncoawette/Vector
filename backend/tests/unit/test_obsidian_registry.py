from __future__ import annotations

from pathlib import Path

import pytest

from vector.memory import HashEmbedder, SqliteMemoryStore
from vector.store import connect
from vector.tools.builder import build_registry_for
from vector.tools.errors import ToolDenied
from vector.tools.files import FileGuard
from vector.tools.obsidian import ObsidianVault


@pytest.fixture()
def setup(tmp_path: Path):
    conn = connect(tmp_path / "v.db", check_integrity=False)
    memory = SqliteMemoryStore(conn, HashEmbedder())
    read_root = tmp_path / "home"
    read_root.mkdir()
    guard = FileGuard(read_root=read_root, write_root=read_root / "ws")
    vault = ObsidianVault(root=tmp_path / "vault")
    vault.write("Stratus Roadmap", "the plan")
    yield {"conn": conn, "memory": memory, "guard": guard, "vault": vault}
    conn.close()


def test_research_agent_gets_full_obsidian_access(setup):
    reg = build_registry_for(
        "research", guard=setup["guard"], memory=setup["memory"], obsidian=setup["vault"]
    )
    names = {t["name"] for t in reg.list()}
    assert {"obsidian.read", "obsidian.write", "obsidian.append", "obsidian.search", "obsidian.list", "obsidian.backlinks"} <= names


def test_writer_agent_gets_full_obsidian_access(setup):
    reg = build_registry_for(
        "writer", guard=setup["guard"], memory=setup["memory"], obsidian=setup["vault"]
    )
    names = {t["name"] for t in reg.list()}
    assert "obsidian.write" in names
    assert "obsidian.append" in names


def test_code_agent_gets_read_only(setup):
    reg = build_registry_for(
        "code", guard=setup["guard"], memory=setup["memory"], obsidian=setup["vault"]
    )
    names = {t["name"] for t in reg.list()}
    assert "obsidian.read" in names
    assert "obsidian.search" in names
    assert "obsidian.write" not in names
    assert "obsidian.append" not in names


def test_security_agent_read_only(setup):
    reg = build_registry_for(
        "security", guard=setup["guard"], memory=setup["memory"], obsidian=setup["vault"]
    )
    names = {t["name"] for t in reg.list()}
    assert "obsidian.read" in names
    assert "obsidian.write" not in names


def test_code_cannot_call_write_via_registry(setup):
    reg = build_registry_for(
        "code", guard=setup["guard"], memory=setup["memory"], obsidian=setup["vault"]
    )
    with pytest.raises(ToolDenied, match="unknown tool"):
        reg.call("obsidian.write", {"title": "x", "body": "y"})


def test_search_via_registry_returns_hits(setup):
    reg = build_registry_for(
        "research", guard=setup["guard"], memory=setup["memory"], obsidian=setup["vault"]
    )
    hits = reg.call("obsidian.search", {"query": "plan", "k": 5})
    assert hits and hits[0]["title"] == "Stratus Roadmap"


def test_write_via_registry_persists_to_disk(setup):
    reg = build_registry_for(
        "writer", guard=setup["guard"], memory=setup["memory"], obsidian=setup["vault"]
    )
    reg.call("obsidian.write", {"title": "new note", "body": "fresh"})
    assert setup["vault"].read("new note")["text"] == "fresh"


def test_search_args_bounded(setup):
    reg = build_registry_for(
        "research", guard=setup["guard"], memory=setup["memory"], obsidian=setup["vault"]
    )
    with pytest.raises(ToolDenied):
        reg.call("obsidian.search", {"query": "", "k": 5})
    with pytest.raises(ToolDenied):
        reg.call("obsidian.search", {"query": "x", "k": 99})


def test_no_vault_means_no_obsidian_tools(setup):
    reg = build_registry_for(
        "research", guard=setup["guard"], memory=setup["memory"], obsidian=None
    )
    names = {t["name"] for t in reg.list()}
    assert "obsidian.read" not in names
    assert "obsidian.search" not in names
