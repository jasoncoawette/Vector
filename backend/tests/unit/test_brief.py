from __future__ import annotations

from datetime import datetime

from vector.engine.brief import MAX_SECONDS, estimated_seconds, render_morning_brief
from vector.engine.picker import Pick
from vector.store.tasks import Task


def _task(i: int, title: str) -> Task:
    return Task(
        id=i,
        title=title,
        source="linear",
        tag="outcome",
        priority=1,
        mission="stratus",
        status="open",
    )


def _picks() -> list[Pick]:
    return [
        Pick(task=_task(1, "Ship CLI"), score=2.0, reason="Ship CLI: outcome work"),
        Pick(
            task=_task(2, "LOI follow-up"),
            score=1.5,
            reason="LOI follow-up: Stratus aligned, outcome work",
        ),
        Pick(
            task=_task(3, "Lattice link"),
            score=1.2,
            reason="Lattice link: high priority",
        ),
    ]


def test_brief_mentions_user_and_three_picks():
    text = render_morning_brief(_picks(), now=datetime(2026, 5, 12, 5, 0))
    assert "Jason" in text
    assert "Ship CLI" in text
    assert "LOI follow-up" in text
    assert "Lattice link" in text


def test_brief_fits_under_target_audio_length():
    text = render_morning_brief(_picks(), now=datetime(2026, 5, 12, 5, 0))
    assert estimated_seconds(text) < MAX_SECONDS


def test_brief_with_no_picks_handles_gracefully():
    text = render_morning_brief([], now=datetime(2026, 5, 12, 5, 0))
    assert "No picks" in text


def test_brief_picks_greeting_by_hour():
    assert "morning" in render_morning_brief(_picks(), now=datetime(2026, 5, 12, 5, 0))
    assert "afternoon" in render_morning_brief(_picks(), now=datetime(2026, 5, 12, 13, 0))
    assert "evening" in render_morning_brief(_picks(), now=datetime(2026, 5, 12, 21, 0))
