from __future__ import annotations

import asyncio
import inspect
import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Literal

logger = logging.getLogger("vector.hooks")

HookEvent = Literal[
    "tool_call_complete",
    "agent_complete",
    "pick_override",
    "routing_decision",
    "voice_turn_complete",
]

Listener = Callable[[dict], Awaitable[None] | None]


@dataclass
class HookRegistry:
    _listeners: dict[str, list[Listener]] = field(default_factory=dict)

    def on(self, event: HookEvent, listener: Listener) -> Callable[[], None]:
        bucket = self._listeners.setdefault(event, [])
        bucket.append(listener)

        def unsubscribe() -> None:
            try:
                bucket.remove(listener)
            except ValueError:
                pass

        return unsubscribe

    def listener_count(self, event: HookEvent) -> int:
        return len(self._listeners.get(event, []))

    async def emit(self, event: HookEvent, payload: dict) -> None:
        listeners = list(self._listeners.get(event, ()))
        if not listeners:
            return
        for listener in listeners:
            try:
                result = listener(payload)
                if inspect.isawaitable(result):
                    await result
            except Exception as e:  # noqa: BLE001 — hooks must never crash callers
                logger.warning("hook %s listener failed: %s", event, e)

    def emit_nowait(self, event: HookEvent, payload: dict) -> None:
        """Fire-and-forget variant for sync call sites.

        Sync listeners run inline. Async listeners are scheduled on the
        running loop if one exists; otherwise dropped with a warning so
        non-async paths don't block.
        """
        listeners = list(self._listeners.get(event, ()))
        if not listeners:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        for listener in listeners:
            try:
                result = listener(payload)
                if inspect.isawaitable(result):
                    if loop is None:
                        logger.debug("dropped async hook %s: no running loop", event)
                        result.close() if hasattr(result, "close") else None
                    else:
                        loop.create_task(result)
            except Exception as e:  # noqa: BLE001
                logger.warning("hook %s listener failed: %s", event, e)


_default: HookRegistry | None = None


def get_hooks() -> HookRegistry:
    global _default
    if _default is None:
        _default = HookRegistry()
    return _default


def set_hooks(registry: HookRegistry | None) -> None:
    global _default
    _default = registry
