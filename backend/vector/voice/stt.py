from __future__ import annotations

from typing import AsyncIterator, Protocol


class STT(Protocol):
    async def transcribe(self, audio: bytes) -> str: ...
    async def stream(self, chunks: AsyncIterator[bytes]) -> AsyncIterator[str]: ...


class WhisperSTT:
    def __init__(self, model_path: str = "whisper-small") -> None:
        self.model_path = model_path

    async def transcribe(self, audio: bytes) -> str:
        return ""

    async def stream(self, chunks: AsyncIterator[bytes]) -> AsyncIterator[str]:
        async for _ in chunks:
            yield ""
