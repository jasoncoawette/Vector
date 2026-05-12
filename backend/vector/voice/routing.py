from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

HARD_KEYWORDS = (
    "architecture",
    "design doc",
    "security",
    "threat model",
    "refactor",
    "migration",
    "schema",
    "tradeoff",
    "tradeoffs",
    "decision",
    "consequences",
    "audit",
    "incident",
    "post-mortem",
    "kill chain",
    "ITAR",
)

MEDIUM_KEYWORDS = (
    "implement",
    "write",
    "fix",
    "debug",
    "review",
    "extend",
    "explain why",
    "compare",
    "plan",
    "test",
)

SIMPLE_KEYWORDS = (
    "rename",
    "format",
    "list",
    "show",
    "summarize",
    "look up",
    "ping",
    "status",
)

CODE_PATTERN = re.compile(r"```|def |class |\bimport\b|\bSELECT\b|\bUPDATE\b", re.I)


class Tier(str, Enum):
    HAIKU = "haiku"
    SONNET = "sonnet"
    OPUS = "opus"


TIER_MODELS: dict[Tier, str] = {
    Tier.HAIKU: "claude-haiku-4-5-20251001",
    Tier.SONNET: "claude-sonnet-4-6",
    Tier.OPUS: "claude-opus-4-7",
}

THRESH_SIMPLE = 0.30
THRESH_HARD = 0.70


@dataclass
class RoutingDecision:
    tier: Tier
    model: str
    score: float
    features: dict[str, float]
    source: str  # "heuristic" or "bandit" or "override"


def complexity_score(prompt: str, *, agent_type: str | None = None) -> tuple[float, dict[str, float]]:
    """Return a [0,1] complexity score plus the feature breakdown.

    Heuristic only — pairs with the bandit in `bandit.py` for refinement.
    """
    feats: dict[str, float] = {}
    text = prompt.lower()
    words = max(1, len(prompt.split()))

    feats["length"] = min(1.0, words / 400)
    feats["hard_kw"] = min(1.0, sum(1 for k in HARD_KEYWORDS if k in text) / 3)
    feats["medium_kw"] = min(1.0, sum(1 for k in MEDIUM_KEYWORDS if k in text) / 3)
    feats["simple_kw"] = min(1.0, sum(1 for k in SIMPLE_KEYWORDS if k in text) / 2)
    feats["has_code"] = 1.0 if CODE_PATTERN.search(prompt) else 0.0
    feats["agent_code"] = 1.0 if agent_type == "code" else 0.0
    feats["agent_security"] = 1.0 if agent_type == "security" else 0.0

    score = (
        0.20 * feats["length"]
        + 0.30 * feats["hard_kw"]
        + 0.10 * feats["medium_kw"]
        - 0.20 * feats["simple_kw"]
        + 0.10 * feats["has_code"]
        + 0.15 * feats["agent_code"]
        + 0.20 * feats["agent_security"]
    )
    score = max(0.0, min(1.0, score))
    return score, feats


def tier_for_score(score: float) -> Tier:
    if score < THRESH_SIMPLE:
        return Tier.HAIKU
    if score < THRESH_HARD:
        return Tier.SONNET
    return Tier.OPUS


def heuristic_route(prompt: str, *, agent_type: str | None = None) -> RoutingDecision:
    score, feats = complexity_score(prompt, agent_type=agent_type)
    tier = tier_for_score(score)
    return RoutingDecision(
        tier=tier, model=TIER_MODELS[tier], score=score, features=feats, source="heuristic"
    )
