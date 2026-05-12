from __future__ import annotations

import os
from pathlib import Path

import pytest

from vector.tools.errors import NeedsConfirm, ToolDenied
from vector.tools.files import FileGuard


@pytest.fixture()
def guard(tmp_path: Path) -> FileGuard:
    read_root = tmp_path / "home"
    write_root = read_root / "workspace"
    read_root.mkdir()
    return FileGuard(read_root=read_root, write_root=write_root)


def test_read_inside_scope(guard: FileGuard) -> None:
    p = guard.read_root / "note.txt"
    p.write_text("hello")
    out = guard.read(str(p))
    assert out["text"] == "hello"
    assert out["binary"] is False


def test_read_outside_scope_is_denied(guard: FileGuard, tmp_path: Path) -> None:
    outside = tmp_path / "other.txt"
    outside.write_text("nope")
    with pytest.raises(ToolDenied, match="outside read scope"):
        guard.read(str(outside))


def test_symlink_escape_is_denied(guard: FileGuard, tmp_path: Path) -> None:
    outside = tmp_path / "secret.txt"
    outside.write_text("classified")
    link = guard.read_root / "shortcut"
    os.symlink(outside, link)
    with pytest.raises(ToolDenied):
        guard.read(str(link))


def test_hard_block_ssh(tmp_path: Path) -> None:
    read_root = tmp_path / "home"
    ssh = read_root / ".ssh"
    ssh.mkdir(parents=True)
    key = ssh / "id_rsa"
    key.write_text("KEY")
    g = FileGuard(read_root=read_root, write_root=read_root / "workspace")
    with pytest.raises(ToolDenied, match="hard-blocked"):
        g.read(str(key))


def test_binary_file_returns_metadata_only(guard: FileGuard) -> None:
    p = guard.read_root / "img.bin"
    p.write_bytes(b"\x00\x01\x02\x03")
    out = guard.read(str(p))
    assert out["binary"] is True
    assert out["text"] is None


def test_write_inside_workspace(guard: FileGuard) -> None:
    target = guard.write_root / "draft.md"
    out = guard.write(str(target), "draft")
    assert Path(out["path"]).read_text() == "draft"


def test_write_outside_workspace_needs_confirm(guard: FileGuard) -> None:
    target = guard.read_root / "outside-ws.md"
    with pytest.raises(ToolDenied, match="confirm"):
        guard.write(str(target), "x")
    guard.write(str(target), "x", confirm=True)
    assert target.read_text() == "x"


def test_write_outside_all_scope_is_denied(guard: FileGuard, tmp_path: Path) -> None:
    target = tmp_path / "evil.txt"
    with pytest.raises(ToolDenied, match="outside any scope"):
        guard.write(str(target), "x", confirm=True)


def test_delete_requires_two_steps(guard: FileGuard) -> None:
    target = guard.write_root / "kill.txt"
    target.write_text("doomed")
    with pytest.raises(NeedsConfirm) as exc:
        guard.request_delete(str(target))
    token = exc.value.token
    out = guard.confirm_delete(str(target), token)
    assert out["deleted"] is True
    assert not target.exists()


def test_delete_token_cannot_be_reused(guard: FileGuard) -> None:
    target = guard.write_root / "kill.txt"
    target.write_text("doomed")
    with pytest.raises(NeedsConfirm) as exc:
        guard.request_delete(str(target))
    token = exc.value.token
    guard.confirm_delete(str(target), token)
    target.write_text("again")
    with pytest.raises(ToolDenied, match="invalid"):
        guard.confirm_delete(str(target), token)


def test_delete_token_path_must_match(guard: FileGuard) -> None:
    a = guard.write_root / "a.txt"
    b = guard.write_root / "b.txt"
    a.write_text("a")
    b.write_text("b")
    with pytest.raises(NeedsConfirm) as exc:
        guard.request_delete(str(a))
    with pytest.raises(ToolDenied):
        guard.confirm_delete(str(b), exc.value.token)


def test_workspace_must_be_inside_read_root(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        FileGuard(read_root=tmp_path / "a", write_root=tmp_path / "b")


def test_large_file_returns_summary_mode(guard: FileGuard, monkeypatch) -> None:
    from vector.tools import files as files_mod

    monkeypatch.setattr(files_mod, "MAX_INLINE_BYTES", 16)
    p = guard.read_root / "big.txt"
    p.write_text("x" * 64)
    out = guard.read(str(p))
    assert out.get("summary_mode") is True
    assert len(out["text"]) <= 4096
