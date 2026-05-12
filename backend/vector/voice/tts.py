from __future__ import annotations

from typing import AsyncIterator, Protocol

import httpx


class TTS(Protocol):
    async def stream(self, text: str) -> AsyncIterator[bytes]: ...


class PiperFallbackTTS:
    """Local fallback when ElevenLabs is down (PRD §14.1)."""

    async def stream(self, text: str) -> AsyncIterator[bytes]:
        if False:
            yield b""
        return


class ElevenLabsTTS:
    """Streaming TTS over the ElevenLabs HTTP API.

    `http` is injected for testing. Production code passes an
    `httpx.AsyncClient`; tests pass a fake stream object.
    """

    API_URL = "https://api.elevenlabs.io/v1/text-to-speech"

    def __init__(
        self,
        api_key: str,
        *,
        voice_id: str = "default",
        model: str = "eleven_turbo_v2",
        http: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("ElevenLabs API key required")
        if not voice_id:
            raise ValueError("voice_id required")
        self._api_key = api_key
        self.voice_id = voice_id
        self.model = model
        self._http = http

    async def stream(self, text: str) -> AsyncIterator[bytes]:
        if not text.strip():
            return
        client = self._http or httpx.AsyncClient(timeout=30.0)
        try:
            payload = {"text": text, "model_id": self.model}
            headers = {
                "xi-api-key": self._api_key,
                "accept": "audio/mpeg",
                "content-type": "application/json",
            }
            url = f"{self.API_URL}/{self.voice_id}/stream"
            async with client.stream("POST", url, json=payload, headers=headers) as resp:
                resp.raise_for_status()
                async for chunk in resp.aiter_bytes():
                    if chunk:
                        yield chunk
        finally:
            if self._http is None:
                await client.aclose()
