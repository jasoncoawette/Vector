from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import AsyncIterator, Protocol

SAMPLE_RATE = 16_000


class STT(Protocol):
    async def transcribe(self, audio: bytes) -> str: ...
    async def stream(self, chunks: AsyncIterator[bytes]) -> AsyncIterator[str]: ...


@dataclass
class FakeSTT:
    """Scripted STT for tests. Returns canned strings on each call."""

    transcripts: list[str] = field(default_factory=list)

    async def transcribe(self, audio: bytes) -> str:
        if not self.transcripts:
            return ""
        return self.transcripts.pop(0)

    async def stream(self, chunks: AsyncIterator[bytes]) -> AsyncIterator[str]:
        collected = bytearray()
        async for chunk in chunks:
            collected.extend(chunk)
        yield await self.transcribe(bytes(collected))


class WhisperSTT:
    """Local STT via whisper.cpp (pywhispercpp binding).

    Audio bytes never leave the laptop (PRD §14.9). The binding is loaded
    lazily so test suites and CI don't need to install whisper.cpp.

    `model` is a whisper.cpp model name (e.g. "small.en", "base.en").
    """

    def __init__(self, model: str = "small.en", *, sample_rate: int = SAMPLE_RATE) -> None:
        if not model:
            raise ValueError("model required")
        if sample_rate not in (8_000, 16_000, 32_000, 48_000):
            raise ValueError("sample_rate must be one of 8/16/32/48 kHz")
        self.model = model
        self.sample_rate = sample_rate
        self._engine = None

    def _load(self) -> None:
        if self._engine is not None:
            return
        from pywhispercpp.model import Model  # type: ignore[import-not-found]

        self._engine = Model(self.model, print_realtime=False, print_progress=False)

    async def transcribe(self, audio: bytes) -> str:
        if not audio:
            return ""

        def _run() -> str:
            self._load()
            segments = self._engine.transcribe(audio)
            return " ".join(s.text.strip() for s in segments).strip()

        return await asyncio.to_thread(_run)

    async def stream(self, chunks: AsyncIterator[bytes]) -> AsyncIterator[str]:
        buf = bytearray()
        async for chunk in chunks:
            buf.extend(chunk)
            # Yield a partial transcript every ~1s of audio (16kHz * 2 bytes).
            if len(buf) >= self.sample_rate * 2:
                text = await self.transcribe(bytes(buf))
                buf.clear()
                if text:
                    yield text
        if buf:
            text = await self.transcribe(bytes(buf))
            if text:
                yield text
