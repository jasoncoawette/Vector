from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from .brain import Brain, BrainReply


@dataclass
class LoopResult:
    text: str
    aborted: bool = False
    reason: str = ""
    cost_usd: float = 0.0
    calls: list[dict] = field(default_factory=list)


def _call_signature(call: dict) -> tuple:
    return (call.get("name"), tuple(sorted((call.get("args") or {}).items())))


async def run_turn(
    brain: Brain,
    prompt: str,
    *,
    timeout_s: int = 30,
    loop_call_cap: int = 5,
    cost_cap_usd: float = 1.0,
) -> LoopResult:
    result = LoopResult(text="")
    history: list[dict] = []
    last_signature: tuple | None = None
    repeat_count = 0

    async def loop_body() -> None:
        nonlocal last_signature, repeat_count
        while True:
            reply: BrainReply = await brain.plan(prompt, history)
            result.cost_usd += reply.cost_usd
            if result.cost_usd > cost_cap_usd:
                result.aborted = True
                result.reason = "cost_cap"
                return
            if reply.tool_call:
                sig = _call_signature(reply.tool_call)
                if sig == last_signature:
                    repeat_count += 1
                else:
                    repeat_count = 1
                    last_signature = sig
                if repeat_count >= loop_call_cap:
                    result.aborted = True
                    result.reason = "loop_detected"
                    return
                result.calls.append(reply.tool_call)
                history.append({"role": "tool", "call": reply.tool_call})
                continue
            result.text = reply.text
            if reply.final:
                return

    try:
        await asyncio.wait_for(loop_body(), timeout=timeout_s)
    except asyncio.TimeoutError:
        result.aborted = True
        result.reason = "timeout"
    return result
