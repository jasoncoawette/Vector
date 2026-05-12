from __future__ import annotations

import pytest

from vector.voice.tts import ElevenLabsTTS, PiperFallbackTTS


class _FakeResponse:
    def __init__(self, chunks: list[bytes], status: int = 200) -> None:
        self._chunks = chunks
        self.status_code = status

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"http {self.status_code}")

    async def aiter_bytes(self):
        for c in self._chunks:
            yield c


class _StreamCtx:
    def __init__(self, response: _FakeResponse) -> None:
        self._r = response

    async def __aenter__(self) -> _FakeResponse:
        return self._r

    async def __aexit__(self, *args) -> None:
        pass


class FakeHttp:
    def __init__(self, response: _FakeResponse) -> None:
        self._r = response
        self.last_url = ""
        self.last_headers: dict = {}
        self.last_payload: dict = {}

    def stream(self, method, url, *, json, headers):
        self.last_url = url
        self.last_headers = headers
        self.last_payload = json
        return _StreamCtx(self._r)


async def test_streams_audio_chunks():
    http = FakeHttp(_FakeResponse([b"\x01\x02", b"\x03"]))
    tts = ElevenLabsTTS(api_key="k", voice_id="v1", http=http)  # type: ignore[arg-type]
    out: list[bytes] = []
    async for chunk in tts.stream("hello"):
        out.append(chunk)
    assert b"".join(out) == b"\x01\x02\x03"


async def test_uses_voice_id_in_url():
    http = FakeHttp(_FakeResponse([b"a"]))
    tts = ElevenLabsTTS(api_key="k", voice_id="vX", http=http)  # type: ignore[arg-type]
    async for _ in tts.stream("hi"):
        pass
    assert "/vX/stream" in http.last_url


async def test_sends_api_key_header_not_logged():
    http = FakeHttp(_FakeResponse([b"a"]))
    tts = ElevenLabsTTS(api_key="secret-key", voice_id="v", http=http)  # type: ignore[arg-type]
    async for _ in tts.stream("hi"):
        pass
    assert http.last_headers.get("xi-api-key") == "secret-key"
    # Repr should not leak the key.
    assert "secret-key" not in repr(tts)


async def test_empty_text_yields_nothing():
    http = FakeHttp(_FakeResponse([b"x"]))
    tts = ElevenLabsTTS(api_key="k", voice_id="v", http=http)  # type: ignore[arg-type]
    out: list[bytes] = []
    async for c in tts.stream("   "):
        out.append(c)
    assert out == []


async def test_http_error_propagates():
    http = FakeHttp(_FakeResponse([], status=500))
    tts = ElevenLabsTTS(api_key="k", voice_id="v", http=http)  # type: ignore[arg-type]
    with pytest.raises(RuntimeError):
        async for _ in tts.stream("hi"):
            pass


def test_rejects_empty_key():
    with pytest.raises(ValueError):
        ElevenLabsTTS(api_key="")


def test_rejects_empty_voice():
    with pytest.raises(ValueError):
        ElevenLabsTTS(api_key="k", voice_id="")


async def test_piper_fallback_is_silent_for_now():
    tts = PiperFallbackTTS()
    out: list[bytes] = []
    async for c in tts.stream("anything"):
        out.append(c)
    assert out == []
