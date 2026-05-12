"""Cheap success-criteria verifier on the Haiku tier.

After each attempt, the verifier brain reads (criteria, output) and
returns a `Verdict`. If `success=False`, its `reason` is fed into the
next retry as feedback. Verifier calls are intentionally bounded: a
single brain call, no tool access, no loop.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Protocol


@dataclass
class Verdict:
    success: bool
    reason: str
    cost_usd: float = 0.0


class Verifier(Protocol):
    async def check(self, criteria: str, output: str) -> Verdict: ...


VERIFIER_SYSTEM = (
    "You are a strict acceptance checker. Given a success criterion and an "
    "agent's output, answer in this JSON shape exactly: "
    '{"success": true|false, "reason": "<one short sentence>"}. '
    "Pass only if the criterion is clearly met. When in doubt, fail and say why."
)


class FakeVerifier:
    """Scripted verifier for tests. Pops verdicts in order."""

    def __init__(self, verdicts: list[Verdict]) -> None:
        self._verdicts = list(verdicts)

    async def check(self, criteria: str, output: str) -> Verdict:
        if not self._verdicts:
            return Verdict(success=True, reason="default-pass")
        return self._verdicts.pop(0)


@dataclass
class ClaudeVerifier:
    """Real verifier backed by a Brain (typically Haiku-tier).

    Returns a Verdict by parsing JSON from the brain's reply. Malformed
    replies fail closed (success=False) — agents should not be accepted
    when the verifier itself is unclear.
    """

    brain_factory: Callable[[str], Any]

    async def check(self, criteria: str, output: str) -> Verdict:
        prompt = (
            f"Criterion:\n{criteria}\n\n"
            f"Agent output:\n{output[:6000]}\n\n"
            "Return your verdict as JSON only."
        )
        brain = self.brain_factory("verifier")
        reply = await brain.plan(prompt, [])
        text = (reply.text or "").strip()
        try:
            data = _extract_json(text)
        except ValueError as e:
            return Verdict(success=False, reason=f"verifier parse failed: {e}", cost_usd=reply.cost_usd)
        if not isinstance(data, dict) or "success" not in data:
            return Verdict(success=False, reason="verifier returned no success field", cost_usd=reply.cost_usd)
        return Verdict(
            success=bool(data.get("success")),
            reason=str(data.get("reason", ""))[:400],
            cost_usd=reply.cost_usd,
        )


def _extract_json(text: str) -> dict:
    """Pull the first JSON object out of a reply. Tolerates leading text
    or fenced code blocks."""
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < 0 or end <= start:
        raise ValueError("no JSON object found")
    return json.loads(text[start : end + 1])
