from __future__ import annotations

from datetime import datetime

from .picker import Pick

WORDS_PER_SECOND = 2.7
MAX_SECONDS = 60


def _greeting(now: datetime, user: str) -> str:
    if now.hour < 12:
        return f"Good morning {user}."
    if now.hour < 18:
        return f"Good afternoon {user}."
    return f"Good evening {user}."


def _ordinal(n: int) -> str:
    return {1: "First", 2: "Second", 3: "Third"}.get(n, f"{n}th")


def render_morning_brief(
    picks: list[Pick],
    *,
    now: datetime,
    user: str = "Jason",
    block_minutes: int = 135,
) -> str:
    if not picks:
        return f"{_greeting(now, user)} No picks today. Add tasks or sync Linear."
    per_task = max(15, block_minutes // max(len(picks), 1))
    lines = [_greeting(now, user), f"Three picks for the {block_minutes}-minute block."]
    for i, p in enumerate(picks, start=1):
        lines.append(f"{_ordinal(i)}: {p.reason} About {per_task} minutes.")
    lines.append("Say 'swap' to override. Say 'start' to begin.")
    return " ".join(lines)


def estimated_seconds(text: str) -> float:
    words = len(text.split())
    return words / WORDS_PER_SECOND
