from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any, Callable

from pydantic import BaseModel, ValidationError

from .errors import ToolDenied, ToolError

Handler = Callable[[BaseModel], Any]


@dataclass
class Tool:
    name: str
    schema: type[BaseModel]
    handler: Handler
    description: str = ""


class Registry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def list(self) -> list[dict]:
        return [
            {"name": t.name, "description": t.description}
            for t in self._tools.values()
        ]

    def _dispatch(self, name: str, args: dict[str, Any]) -> Any:
        tool = self._tools.get(name)
        if tool is None:
            raise ToolDenied(f"unknown tool: {name}")
        try:
            parsed = tool.schema.model_validate(args)
        except ValidationError as e:
            raise ToolDenied(f"bad args for {name}: {e.errors()}") from e
        return tool, parsed

    def call(self, name: str, args: dict[str, Any]) -> Any:
        """Sync dispatch. If the handler is async, returns the coroutine
        unawaited — callers from an async context should use `acall`."""
        tool, parsed = self._dispatch(name, args)
        try:
            return tool.handler(parsed)
        except ToolError:
            raise
        except Exception as e:
            raise ToolError(f"{name} failed: {e}") from e

    async def acall(self, name: str, args: dict[str, Any]) -> Any:
        """Async dispatch. Awaits coroutine-returning handlers; passes
        sync handler returns straight through."""
        tool, parsed = self._dispatch(name, args)
        try:
            result = tool.handler(parsed)
            if inspect.isawaitable(result):
                result = await result
            return result
        except ToolError:
            raise
        except Exception as e:
            raise ToolError(f"{name} failed: {e}") from e
