from __future__ import annotations

import os
from pathlib import Path

import pytest

from vector.tools.errors import ToolDenied
from vector.tools.obsidian import MAX_NOTE_BYTES, ObsidianVault


@pytest.fixture()
def vault(tmp_path: Path) -> ObsidianVault:
    return ObsidianVault(root=tmp_path / "vault")


def test_creates_root_if_missing(tmp_path: Path) -> None:
    v = ObsidianVault(root=tmp_path / "newvault")
    assert (tmp_path / "newvault").is_dir()


def test_root_must_be_dir(tmp_path: Path) -> None:
    target = tmp_path / "file"
    target.write_text("not a dir")
    with pytest.raises(ValueError):
        ObsidianVault(root=target)


def test_write_then_read_round_trips(vault: ObsidianVault) -> None:
    vault.write("Stratus Roadmap", "# Roadmap\n\n- ship CLI\n")
    out = vault.read("Stratus Roadmap")
    assert "# Roadmap" in out["text"]
    assert out["title"] == "Stratus Roadmap"


def test_write_accepts_optional_md_suffix(vault: ObsidianVault) -> None:
    vault.write("plain.md", "body")
    vault.write("also-fine", "body")
    titles = set(vault.list_notes())
    assert "plain" in titles
    assert "also-fine" in titles


def test_folder_titles_supported(vault: ObsidianVault) -> None:
    vault.write("decisions/2026/Q2 plan", "draft")
    out = vault.read("decisions/2026/Q2 plan")
    assert out["text"] == "draft"
    assert "decisions/2026/Q2 plan" in vault.list_notes()


def test_traversal_denied(vault: ObsidianVault) -> None:
    with pytest.raises(ToolDenied, match="outside vault"):
        vault.write("../escape", "no")
    with pytest.raises(ToolDenied, match="outside vault"):
        vault.read("../../etc/passwd")


def test_absolute_path_denied(vault: ObsidianVault) -> None:
    with pytest.raises(ToolDenied):
        vault.read("/etc/passwd")


def test_symlink_escape_denied(tmp_path: Path, vault: ObsidianVault) -> None:
    secret = tmp_path / "secret.md"
    secret.write_text("classified")
    os.symlink(secret, vault.root / "shortcut.md")
    with pytest.raises(ToolDenied):
        vault.read("shortcut")


def test_empty_name_denied(vault: ObsidianVault) -> None:
    with pytest.raises(ToolDenied):
        vault.write("", "x")
    with pytest.raises(ToolDenied):
        vault.write("   ", "x")


def test_oversize_write_denied(vault: ObsidianVault) -> None:
    huge = "x" * (MAX_NOTE_BYTES + 1)
    with pytest.raises(ToolDenied, match="exceeds"):
        vault.write("big", huge)


def test_append_creates_when_missing(vault: ObsidianVault) -> None:
    vault.append("Daily/2026-05-12", "morning thoughts")
    out = vault.read("Daily/2026-05-12")
    assert out["text"] == "morning thoughts"


def test_append_adds_newline_between_chunks(vault: ObsidianVault) -> None:
    vault.write("Daily/2026-05-12", "morning thoughts")
    vault.append("Daily/2026-05-12", "afternoon update")
    out = vault.read("Daily/2026-05-12")
    assert out["text"] == "morning thoughts\nafternoon update"


def test_append_preserves_trailing_newline(vault: ObsidianVault) -> None:
    vault.write("note", "first\n")
    vault.append("note", "second")
    assert vault.read("note")["text"] == "first\nsecond"


def test_search_finds_substring_case_insensitive(vault: ObsidianVault) -> None:
    vault.write("Anduril", "We integrate with the Lattice platform daily")
    vault.write("Groceries", "milk, eggs, bread")
    hits = vault.search("lattice")
    assert len(hits) == 1
    assert hits[0].title == "Anduril"
    assert "Lattice" in hits[0].snippet


def test_search_returns_line_number(vault: ObsidianVault) -> None:
    vault.write("note", "line 1\nline 2\nKILL CHAIN is here\nline 4")
    hits = vault.search("kill chain")
    assert hits[0].line == 3


def test_search_k_clamps(vault: ObsidianVault) -> None:
    for i in range(30):
        vault.write(f"n{i}", "target everywhere")
    hits = vault.search("target", k=999)
    assert len(hits) <= 20


def test_search_empty_query_denied(vault: ObsidianVault) -> None:
    with pytest.raises(ToolDenied):
        vault.search("")
    with pytest.raises(ToolDenied):
        vault.search("   ")


def test_backlinks_finds_wikilinks(vault: ObsidianVault) -> None:
    vault.write("AFWERX", "see [[Stratus Roadmap]]")
    vault.write("Calendar/Today", "blocking time on [[Stratus Roadmap]]")
    vault.write("Stratus Roadmap", "the plan")
    out = vault.backlinks("Stratus Roadmap")
    assert set(out) == {"AFWERX", "Calendar/Today"}


def test_backlinks_handles_alias_and_anchor(vault: ObsidianVault) -> None:
    vault.write("alias-source", "use [[Stratus Roadmap|the plan]]")
    vault.write("anchor-source", "see [[Stratus Roadmap#Q2]]")
    vault.write("Stratus Roadmap", "x")
    out = vault.backlinks("Stratus Roadmap")
    assert set(out) == {"alias-source", "anchor-source"}


def test_backlinks_resolves_leaf_against_folder(vault: ObsidianVault) -> None:
    """`[[Roadmap]]` should resolve to `folder/Roadmap` too."""
    vault.write("notes/Roadmap", "plan")
    vault.write("source", "see [[Roadmap]]")
    out = vault.backlinks("notes/Roadmap")
    assert "source" in out


def test_backlinks_excludes_self(vault: ObsidianVault) -> None:
    vault.write("Loop", "this note refers to [[Loop]]")
    assert vault.backlinks("Loop") == []


def test_list_notes_excludes_non_md(vault: ObsidianVault) -> None:
    vault.write("real", "x")
    (vault.root / "attachment.png").write_bytes(b"\x89PNG")
    titles = vault.list_notes()
    assert "real" in titles
    assert "attachment" not in titles
    assert all(not t.endswith(".png") for t in titles)


def test_read_missing_denied(vault: ObsidianVault) -> None:
    with pytest.raises(ToolDenied, match="not found"):
        vault.read("nope")


def test_read_directory_denied(vault: ObsidianVault) -> None:
    (vault.root / "folder").mkdir()
    with pytest.raises(ToolDenied):
        vault.read("folder")
