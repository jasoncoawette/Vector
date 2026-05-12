from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class BrainReply:
    text: str = ""
    tool_call: dict | None = None
    final: bool = True
    cost_usd: float = 0.0
    meta: dict = field(default_factory=dict)


class Brain(Protocol):
    async def plan(self, prompt: str, history: list[dict]) -> BrainReply: ...


class ClaudeBrain:
    def __init__(self, api_key: str, model: str) -> None:
        if not api_key:
            raise ValueError("Anthropic API key required")
        self._api_key = api_key
        self.model = model

    async def plan(self, prompt: str, history: list[dict]) -> BrainReply:
        return BrainReply(text="", final=True)


class FakeBrain:
    def __init__(self, replies: list[BrainReply]) -> None:
        self._replies = list(replies)

    async def plan(self, prompt: str, history: list[dict]) -> BrainReply:
        if not self._replies:
            return BrainReply(text="", final=True)
        return self._replies.pop(0)
