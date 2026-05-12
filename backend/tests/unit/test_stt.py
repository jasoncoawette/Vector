from __future__ import annotations

import pytest

from vector.voice.stt import FakeSTT, WhisperSTT


async def test_fake_transcribe_returns_scripted():
    s = FakeSTT(transcripts=["hello vector"])
    assert await s.transcribe(b"\x00" * 32_000) == "hello vector"


async def test_fake_transcribe_empty_when_exhausted():
    s = FakeSTT()
    assert await s.transcribe(b"\x00") == ""


async def test_fake_stream_collects_and_yields():
    async def chunks():
        yield b"\x00\x01"
        yield b"\x02\x03"

    s = FakeSTT(transcripts=["assembled"])
    out: list[str] = []
    async for piece in s.stream(chunks()):
        out.append(piece)
    assert out == ["assembled"]


def test_whisper_rejects_empty_model():
    with pytest.raises(ValueError):
        WhisperSTT(model="")


def test_whisper_rejects_bad_sample_rate():
    with pytest.raises(ValueError):
        WhisperSTT(model="small.en", sample_rate=11_025)


async def test_whisper_transcribe_empty_audio_short_circuits():
    s = WhisperSTT(model="small.en")
    assert await s.transcribe(b"") == ""
