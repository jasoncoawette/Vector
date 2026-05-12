from __future__ import annotations

from typing import AsyncIterator

import pytest
from fastapi.testclient import TestClient

from vector.app import app
from vector.deps import set_session_factory
from vector.voice.brain import BrainReply, FakeBrain
from vector.voice.session import VoiceSession
from vector.voice.stt import FakeSTT


class ScriptedTTS:
    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = chunks

    async def stream(self, text: str) -> AsyncIterator[bytes]:
        for c in self._chunks:
            yield c


@pytest.fixture()
def client():
    def factory() -> VoiceSession:
        return VoiceSession(
            stt=FakeSTT(transcripts=["hello vector"]),
            brain=FakeBrain([BrainReply(text="hi jason", final=True)]),
            tts=ScriptedTTS([b"\x01\x02", b"\x03"]),
        )

    set_session_factory(factory)
    try:
        yield TestClient(app)
    finally:
        set_session_factory(None)


def test_full_turn_over_ws(client):
    with client.websocket_connect("/voice/stream") as ws:
        ws.send_bytes(b"\x00\x00")
        ws.send_text('{"type":"end"}')
        states: list[str] = []
        audio = bytearray()
        reply = ""
        while True:
            msg = ws.receive()
            if "bytes" in msg and msg["bytes"]:
                audio.extend(msg["bytes"])
                continue
            text = msg.get("text")
            if text is None:
                break
            data = __import__("json").loads(text)
            if data.get("kind") == "state":
                states.append(data["state"])
            elif data.get("kind") == "reply":
                reply = data["text"]
            if data.get("kind") == "state" and data["state"] == "idle":
                break

    assert "listen" in states
    assert "think" in states
    assert "speak" in states
    assert states[-1] == "idle"
    assert reply == "hi jason"
    assert bytes(audio) == b"\x01\x02\x03"


def test_empty_transcript_returns_to_idle(client):
    def factory() -> VoiceSession:
        return VoiceSession(
            stt=FakeSTT(transcripts=[""]),
            brain=FakeBrain([BrainReply(text="should never speak", final=True)]),
            tts=ScriptedTTS([b"x"]),
        )

    set_session_factory(factory)
    with TestClient(app).websocket_connect("/voice/stream") as ws:
        ws.send_bytes(b"\x00")
        ws.send_text('{"type":"end"}')
        last_state = None
        while True:
            msg = ws.receive()
            text = msg.get("text")
            if not text:
                break
            data = __import__("json").loads(text)
            if data.get("kind") == "state":
                last_state = data["state"]
                if last_state == "idle":
                    break
        assert last_state == "idle"
    set_session_factory(None)


def test_barge_in_signal_cancels_speech(client):
    import asyncio

    class SlowTTS:
        async def stream(self, text: str):
            for _ in range(100):
                await asyncio.sleep(0.02)
                yield b"x"

    def factory() -> VoiceSession:
        return VoiceSession(
            stt=FakeSTT(transcripts=["read it"]),
            brain=FakeBrain([BrainReply(text="very long answer", final=True)]),
            tts=SlowTTS(),
        )

    set_session_factory(factory)
    try:
        with TestClient(app).websocket_connect("/voice/stream") as ws:
            ws.send_bytes(b"\x00")
            ws.send_text('{"type":"end"}')
            chunks_before_bargein = 0
            sent_bargein = False
            saw_bargein = False
            while True:
                msg = ws.receive()
                if "bytes" in msg and msg["bytes"]:
                    chunks_before_bargein += 1
                    if chunks_before_bargein >= 2 and not sent_bargein:
                        ws.send_text('{"type":"barge_in"}')
                        sent_bargein = True
                    continue
                text = msg.get("text")
                if not text:
                    break
                data = __import__("json").loads(text)
                if data.get("kind") == "bargein":
                    saw_bargein = True
                if data.get("kind") == "state" and data["state"] == "idle":
                    break
            assert saw_bargein is True
    finally:
        set_session_factory(None)
