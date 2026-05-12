from __future__ import annotations

from typing import AsyncIterator, Protocol


class STT(Protocol):
    async def transcribe(self, audio: bytes) -> str: ...
    async def stream(self, chunks: AsyncIterator[bytes]) -> AsyncIterator[str]: ...


class WhisperSTT:
    """Local-only STT via whisper.cpp. Audio bytes never leave the laptop.

    The real binding (e.g. pywhispercpp) is wired at app boot; this
    keeps the interface in place for the loop and the tests.
    """

    def __init__(self, model: str = "small.en") -> None:
        self.model = model

    async def transcribe(self, audio: bytes) -> str:
        return ""

    async def stream(self, chunks: AsyncIterator[bytes]) -> AsyncIterator[str]:
        async for _ in chunks:
            yield ""
