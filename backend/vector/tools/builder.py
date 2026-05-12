from __future__ import annotations

from .files import FileGuard
from .registry import Registry, Tool
from .schemas import FileDeleteArgs, FileReadArgs, FileWriteArgs


def build_default_registry(guard: FileGuard) -> Registry:
    reg = Registry()

    reg.register(
        Tool(
            name="file.read",
            schema=FileReadArgs,
            handler=lambda a: guard.read(a.path),
            description="Read a text file inside scope.",
        )
    )
    reg.register(
        Tool(
            name="file.write",
            schema=FileWriteArgs,
            handler=lambda a: guard.write(a.path, a.content, confirm=a.confirm),
            description="Write to workspace; outside workspace requires confirm.",
        )
    )

    def _delete(args: FileDeleteArgs):
        if args.confirm_token:
            return guard.confirm_delete(args.path, args.confirm_token)
        return guard.request_delete(args.path)

    reg.register(
        Tool(
            name="file.delete",
            schema=FileDeleteArgs,
            handler=_delete,
            description="Two-step delete. First call returns a confirm token.",
        )
    )

    return reg
