from __future__ import annotations

from ..memory import MemoryStore
from .files import FileGuard
from .registry import Registry, Tool
from .schemas import (
    FileDeleteArgs,
    FileReadArgs,
    FileWriteArgs,
    MemoryAddArgs,
    MemorySearchArgs,
)

# Which agent types get memory.search (read) vs memory.add (write).
# Code and tester get read-only; research / writer / security get both.
MEMORY_READ_TYPES = frozenset({"code", "tester", "research", "writer", "security"})
MEMORY_WRITE_TYPES = frozenset({"research", "writer", "security"})


def _add_file_tools(reg: Registry, guard: FileGuard) -> None:
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


def _add_memory_search(reg: Registry, memory: MemoryStore) -> None:
    reg.register(
        Tool(
            name="memory.search",
            schema=MemorySearchArgs,
            handler=lambda a: [
                {
                    "id": m.id,
                    "kind": m.kind,
                    "text": m.text,
                    "score": m.score,
                    "recorded_at": m.recorded_at,
                }
                for m in memory.search(a.query, kind=a.kind, k=a.k)
            ],
            description="Recall prior memories by semantic similarity.",
        )
    )


def _add_memory_add(reg: Registry, memory: MemoryStore) -> None:
    reg.register(
        Tool(
            name="memory.add",
            schema=MemoryAddArgs,
            handler=lambda a: {"id": memory.add(a.kind, a.text, a.meta)},
            description="Persist a new memory for later recall.",
        )
    )


def build_default_registry(guard: FileGuard) -> Registry:
    reg = Registry()
    _add_file_tools(reg, guard)
    return reg


def build_registry_for(
    agent_type: str | None,
    *,
    guard: FileGuard,
    memory: MemoryStore | None = None,
) -> Registry:
    """Return a registry scoped to one agent type's tool needs.

    Files are always available. Memory.search is granted to agents that
    benefit from recall; memory.add only to those that should accumulate
    long-term state (research, writer, security)."""
    reg = Registry()
    _add_file_tools(reg, guard)
    if memory is not None:
        if agent_type in MEMORY_READ_TYPES or agent_type is None:
            _add_memory_search(reg, memory)
        if agent_type in MEMORY_WRITE_TYPES:
            _add_memory_add(reg, memory)
    return reg
