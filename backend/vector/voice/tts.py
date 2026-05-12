from __future__ import annotations

from typing import AsyncIterator, Protocol


class TTS(Protocol):
    async def stream(self, text: str) -> AsyncIterator[bytes]: ...


class ElevenLabsTTS:
    def __init__(self, api_key: str, voice_id: str = "default") -> None:
        if not api_key:
            raise ValueError("ElevenLabs API key required")
        self._api_key = api_key
        self.voice_id = voice_id

    async def stream(self, text: str) -> AsyncIterator[bytes]:
        if False:
            yield b""
        return
