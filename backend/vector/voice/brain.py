from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

PRICE_PER_MTOK_INPUT = {
    "claude-opus-4-7": 15.0,
    "claude-sonnet-4-6": 3.0,
    "claude-haiku-4-5-20251001": 1.0,
}
PRICE_PER_MTOK_OUTPUT = {
    "claude-opus-4-7": 75.0,
    "claude-sonnet-4-6": 15.0,
    "claude-haiku-4-5-20251001": 5.0,
}


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    in_rate = PRICE_PER_MTOK_INPUT.get(model, 3.0)
    out_rate = PRICE_PER_MTOK_OUTPUT.get(model, 15.0)
    return (input_tokens / 1_000_000) * in_rate + (output_tokens / 1_000_000) * out_rate


@dataclass
class BrainReply:
    text: str = ""
    tool_call: dict | None = None
    final: bool = True
    cost_usd: float = 0.0
    meta: dict = field(default_factory=dict)


class Brain(Protocol):
    async def plan(self, prompt: str, history: list[dict]) -> BrainReply: ...


class AnthropicLike(Protocol):
    """Subset of the anthropic SDK we touch. Lets tests pass a fake."""

    async def create(self, **kwargs: Any) -> Any: ...


class ClaudeBrain:
    """Real brain that drives the Anthropic Messages API.

    `client` is injected so tests don't import the SDK. In production
    deps.py builds it as `anthropic.AsyncAnthropic(api_key=...).messages`.
    """

    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        client: AnthropicLike | None = None,
        tool_schemas: list[dict] | None = None,
        max_tokens: int = 1024,
        system: str | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("Anthropic API key required")
        self._api_key = api_key
        self.model = model
        self._client = client
        self._tools = tool_schemas or []
        self._max_tokens = max_tokens
        self._system = system

    async def plan(self, prompt: str, history: list[dict]) -> BrainReply:
        if self._client is None:
            return BrainReply(text="", final=True, meta={"reason": "no client"})

        messages = list(history) + [{"role": "user", "content": prompt}]
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self._max_tokens,
            "messages": messages,
        }
        if self._tools:
            kwargs["tools"] = self._tools
        if self._system:
            kwargs["system"] = self._system

        resp = await self._client.create(**kwargs)

        usage = getattr(resp, "usage", None)
        cost = 0.0
        if usage is not None:
            cost = estimate_cost(
                self.model,
                getattr(usage, "input_tokens", 0),
                getattr(usage, "output_tokens", 0),
            )

        text_parts: list[str] = []
        tool_call: dict | None = None
        for block in getattr(resp, "content", []):
            block_type = getattr(block, "type", None)
            if block_type == "text":
                text_parts.append(getattr(block, "text", ""))
            elif block_type == "tool_use":
                tool_call = {
                    "id": getattr(block, "id", ""),
                    "name": getattr(block, "name", ""),
                    "args": getattr(block, "input", {}) or {},
                }
                break

        stop_reason = getattr(resp, "stop_reason", "end_turn")
        final = tool_call is None and stop_reason != "tool_use"

        return BrainReply(
            text="".join(text_parts),
            tool_call=tool_call,
            final=final,
            cost_usd=cost,
            meta={"stop_reason": stop_reason},
        )


class FakeBrain:
    def __init__(self, replies: list[BrainReply]) -> None:
        self._replies = list(replies)

    async def plan(self, prompt: str, history: list[dict]) -> BrainReply:
        if not self._replies:
            return BrainReply(text="", final=True)
        return self._replies.pop(0)
