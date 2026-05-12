from __future__ import annotations

import pytest

from vector.voice.brain import BrainReply, FakeBrain
from vector.voice.loop import run_turn


async def test_returns_final_text():
    brain = FakeBrain([BrainReply(text="hello", final=True)])
    result = await run_turn(brain, "hi")
    assert result.text == "hello"
    assert not result.aborted


async def test_loop_detection_aborts_on_repeat_calls():
    same = {"name": "file.read", "args": {"path": "/a"}}
    brain = FakeBrain([BrainReply(tool_call=same, final=False) for _ in range(10)])
    result = await run_turn(brain, "go", loop_call_cap=5)
    assert result.aborted
    assert result.reason == "loop_detected"


async def test_cost_cap_aborts():
    brain = FakeBrain(
        [
            BrainReply(text="part", final=False, cost_usd=0.6),
            BrainReply(text="more", final=False, cost_usd=0.6),
            BrainReply(text="done", final=True),
        ]
    )
    result = await run_turn(brain, "go", cost_cap_usd=1.0)
    assert result.aborted
    assert result.reason == "cost_cap"


async def test_timeout_aborts():
    class SlowBrain:
        async def plan(self, prompt, history):
            import asyncio
            await asyncio.sleep(5)
            return BrainReply(final=True)

    result = await run_turn(SlowBrain(), "go", timeout_s=1)
    assert result.aborted
    assert result.reason == "timeout"


def test_claude_brain_rejects_empty_key():
    from vector.voice.brain import ClaudeBrain

    with pytest.raises(ValueError):
        ClaudeBrain(api_key="", model="x")


def test_elevenlabs_rejects_empty_key():
    from vector.voice.tts import ElevenLabsTTS

    with pytest.raises(ValueError):
        ElevenLabsTTS(api_key="")
