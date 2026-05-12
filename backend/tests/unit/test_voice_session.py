from __future__ import annotations

import asyncio
from typing import AsyncIterator

import pytest

from vector.voice.brain import BrainReply, FakeBrain
from vector.voice.session import VoiceEvent, VoiceSession, VoiceState
from vector.voice.stt import FakeSTT


class ScriptedTTS:
    def __init__(self, chunks: list[bytes], *, delay_s: float = 0.0) -> None:
        self._chunks = chunks
        self._delay = delay_s

    async def stream(self, text: str) -> AsyncIterator[bytes]:
        for c in self._chunks:
            if self._delay:
                await asyncio.sleep(self._delay)
            yield c


async def _mic(*chunks: bytes) -> AsyncIterator[bytes]:
    for c in chunks:
        yield c


def _collect(events: list[VoiceEvent]) -> dict[str, list]:
    out: dict[str, list] = {}
    for e in events:
        out.setdefault(e.kind, []).append(e)
    return out


async def test_happy_path_emits_full_state_cycle():
    session = VoiceSession(
        stt=FakeSTT(transcripts=["good morning"]),
        brain=FakeBrain([BrainReply(text="hello jason", final=True)]),
        tts=ScriptedTTS([b"\x01", b"\x02"]),
    )

    events: list[VoiceEvent] = []
    async for e in session.turn(_mic(b"\x00\x00")):
        events.append(e)

    states = [e.state for e in events if e.kind == "state"]
    assert states[0] == VoiceState.LISTEN
    assert VoiceState.THINK in states
    assert VoiceState.SPEAK in states
    assert states[-1] == VoiceState.IDLE

    grouped = _collect(events)
    audio = b"".join(e.audio or b"" for e in grouped["audio"])
    assert audio == b"\x01\x02"
    assert grouped["reply"][0].text == "hello jason"


async def test_empty_transcript_goes_back_to_idle():
    session = VoiceSession(
        stt=FakeSTT(transcripts=[""]),
        brain=FakeBrain([BrainReply(text="should not be heard", final=True)]),
        tts=ScriptedTTS([b"x"]),
    )

    events: list[VoiceEvent] = []
    async for e in session.turn(_mic(b"\x00")):
        events.append(e)

    grouped = _collect(events)
    assert "reply" not in grouped
    assert "audio" not in grouped
    assert events[-1].state == VoiceState.IDLE


async def test_barge_in_cancels_speech():
    session = VoiceSession(
        stt=FakeSTT(transcripts=["read me a long thing"]),
        brain=FakeBrain([BrainReply(text="x" * 200, final=True)]),
        tts=ScriptedTTS([b"a", b"b", b"c"], delay_s=0.05),
    )

    audio_pieces: list[bytes] = []
    saw_bargein = False
    bg = None

    async def consume():
        nonlocal saw_bargein
        async for e in session.turn(_mic(b"\x00")):
            if e.kind == "audio":
                audio_pieces.append(e.audio or b"")
                if not bg:
                    pass
            if e.kind == "bargein":
                saw_bargein = True

    task = asyncio.create_task(consume())
    await asyncio.sleep(0.06)
    session.barge_in()
    await task

    assert saw_bargein is True
    assert b"".join(audio_pieces) != b"abc"


async def test_brain_cost_cap_emits_error():
    session = VoiceSession(
        stt=FakeSTT(transcripts=["expensive"]),
        brain=FakeBrain(
            [BrainReply(text="part", final=False, cost_usd=5.0)]
        ),
        tts=ScriptedTTS([b"x"]),
        cost_cap_usd=1.0,
    )

    events: list[VoiceEvent] = []
    async for e in session.turn(_mic(b"\x00")):
        events.append(e)
    errs = [e for e in events if e.kind == "error"]
    assert errs and "cost_cap" in (errs[0].error or "")
