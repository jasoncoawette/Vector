from __future__ import annotations

from typing import AsyncIterator

import pytest

from vector.voice.brain import BrainReply, FakeBrain
from vector.voice.session import VoiceSession, VoiceState
from vector.voice.stt import FakeSTT


class _ScriptedTTS:
    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = chunks

    async def stream(self, text: str) -> AsyncIterator[bytes]:
        for c in self._chunks:
            yield c


async def _mic(*chunks: bytes) -> AsyncIterator[bytes]:
    for c in chunks:
        yield c


def _collect_kinds(events):
    return [e.kind for e in events]


async def test_clarify_marker_emits_clarify_event_and_lands_in_listen():
    session = VoiceSession(
        stt=FakeSTT(transcripts=["override the morning brief"]),
        brain=FakeBrain(
            [BrainReply(text="[CLARIFY] for today only or going forward?", final=True)]
        ),
        tts=_ScriptedTTS([b"\x01"]),
    )

    events = []
    async for e in session.turn(_mic(b"\x00\x00")):
        events.append(e)

    # Should emit a 'clarify' event (not 'reply').
    kinds = _collect_kinds(events)
    assert "clarify" in kinds
    assert "reply" not in kinds

    clarify = next(e for e in events if e.kind == "clarify")
    assert clarify.text == "for today only or going forward?"
    assert "[CLARIFY]" not in clarify.text

    # Final state should be LISTEN so the next mic chunk starts a new turn.
    final_state = events[-1].state
    assert final_state == VoiceState.LISTEN


async def test_non_clarify_reply_still_lands_in_idle():
    session = VoiceSession(
        stt=FakeSTT(transcripts=["what's first today"]),
        brain=FakeBrain([BrainReply(text="Ship the CLI.", final=True)]),
        tts=_ScriptedTTS([b"\x01"]),
    )

    events = []
    async for e in session.turn(_mic(b"\x00")):
        events.append(e)

    kinds = _collect_kinds(events)
    assert "reply" in kinds
    assert "clarify" not in kinds
    assert events[-1].state == VoiceState.IDLE


async def test_clarify_text_is_what_tts_speaks():
    """The TTS stream should receive the stripped question, not the
    marker-prefixed string. We check via a recording TTS."""
    spoken = []

    class _RecordingTTS:
        async def stream(self, text):
            spoken.append(text)
            for c in [b"\x01"]:
                yield c

    session = VoiceSession(
        stt=FakeSTT(transcripts=["plan my week"]),
        brain=FakeBrain(
            [BrainReply(text="[CLARIFY] do you want Stratus or Boeing focus?", final=True)]
        ),
        tts=_RecordingTTS(),
    )
    async for _ in session.turn(_mic(b"\x00")):
        pass

    assert spoken == ["do you want Stratus or Boeing focus?"]
