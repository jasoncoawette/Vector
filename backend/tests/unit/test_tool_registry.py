from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import BaseModel, Field

from vector.tools.builder import build_default_registry
from vector.tools.errors import NeedsConfirm, ToolDenied
from vector.tools.files import FileGuard
from vector.tools.registry import Registry, Tool


class Echo(BaseModel):
    msg: str = Field(min_length=1)


def test_unknown_tool_is_denied() -> None:
    reg = Registry()
    with pytest.raises(ToolDenied, match="unknown tool"):
        reg.call("nope", {})


def test_bad_args_are_rejected() -> None:
    reg = Registry()
    reg.register(Tool(name="echo", schema=Echo, handler=lambda a: a.msg))
    with pytest.raises(ToolDenied, match="bad args"):
        reg.call("echo", {"msg": ""})


def test_double_register_rejected() -> None:
    reg = Registry()
    reg.register(Tool(name="echo", schema=Echo, handler=lambda a: a.msg))
    with pytest.raises(ValueError):
        reg.register(Tool(name="echo", schema=Echo, handler=lambda a: a.msg))


def test_file_tools_dispatch(tmp_path: Path) -> None:
    read_root = tmp_path / "home"
    read_root.mkdir()
    guard = FileGuard(read_root=read_root, write_root=read_root / "workspace")
    reg = build_default_registry(guard)

    target = guard.write_root / "x.txt"
    reg.call("file.write", {"path": str(target), "content": "hi"})
    out = reg.call("file.read", {"path": str(target)})
    assert out["text"] == "hi"

    with pytest.raises(NeedsConfirm) as exc:
        reg.call("file.delete", {"path": str(target)})
    reg.call("file.delete", {"path": str(target), "confirm_token": exc.value.token})
    assert not target.exists()
