from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import AsyncIterator

from .brain import Brain
from .loop import run_turn
from .stt import STT
from .tts import TTS


class VoiceState(str, Enum):
    IDLE = "idle"
    LISTEN = "listen"
    THINK = "think"
    SPEAK = "speak"
    ERROR = "error"


@dataclass
class VoiceEvent:
    kind: str
    state: VoiceState | None = None
    text: str | None = None
    audio: bytes | None = None
    error: str | None = None


@dataclass
class VoiceSession:
    """One turn from wake-fired through TTS-complete.

    The orchestrator owns transitions; the WebSocket adapter pipes events
    to the frontend and barge-in signals back in.

    Not safe for concurrent `turn()` calls on the same instance; the
    WebSocket adapter builds a fresh session per connection.
    """

    stt: STT
    brain: Brain
    tts: TTS
    turn_timeout_s: int = 30
    cost_cap_usd: float = 1.0

    _state: VoiceState = field(default=VoiceState.IDLE, init=False)
    _barge_in: asyncio.Event = field(default_factory=asyncio.Event, init=False)

    @property
    def state(self) -> VoiceState:
        return self._state

    def barge_in(self) -> None:
        """Signal that the user has started speaking again. The TTS
        streaming loop polls this between chunks and stops cleanly."""
        self._barge_in.set()

    async def turn(
        self, mic_chunks: AsyncIterator[bytes]
    ) -> AsyncIterator[VoiceEvent]:
        self._barge_in.clear()
        self._state = VoiceState.LISTEN
        yield VoiceEvent(kind="state", state=VoiceState.LISTEN)

        transcript_parts: list[str] = []
        try:
            async for piece in self.stt.stream(mic_chunks):
                transcript_parts.append(piece)
                yield VoiceEvent(kind="transcript", text=piece)
        except Exception as e:
            self._state = VoiceState.ERROR
            yield VoiceEvent(kind="error", error=f"stt: {e}", state=VoiceState.ERROR)
            return

        transcript = " ".join(p.strip() for p in transcript_parts).strip()
        if not transcript:
            self._state = VoiceState.IDLE
            yield VoiceEvent(kind="state", state=VoiceState.IDLE)
            return

        self._state = VoiceState.THINK
        yield VoiceEvent(kind="state", state=VoiceState.THINK)

        try:
            result = await run_turn(
                self.brain,
                transcript,
                timeout_s=self.turn_timeout_s,
                cost_cap_usd=self.cost_cap_usd,
            )
        except Exception as e:
            self._state = VoiceState.ERROR
            yield VoiceEvent(kind="error", error=f"brain: {e}", state=VoiceState.ERROR)
            return

        if result.aborted:
            self._state = VoiceState.ERROR
            yield VoiceEvent(
                kind="error", error=result.reason or "aborted", state=VoiceState.ERROR
            )
            return

        spoken = result.text or ""
        if not spoken:
            self._state = VoiceState.IDLE
            yield VoiceEvent(kind="state", state=VoiceState.IDLE)
            return

        # Clarification path: the brain prefixed [CLARIFY] to signal that
        # it would need to guess to answer fully. Speak the question, then
        # land back in LISTEN so the user's follow-up opens a new turn.
        from ..prompts import needs_clarification, strip_clarify_marker

        clarifying = needs_clarification(spoken)
        if clarifying:
            spoken = strip_clarify_marker(spoken)

        self._state = VoiceState.SPEAK
        yield VoiceEvent(kind="state", state=VoiceState.SPEAK)
        yield VoiceEvent(
            kind="clarify" if clarifying else "reply",
            text=spoken,
        )

        try:
            async for audio_chunk in self.tts.stream(spoken):
                if self._barge_in.is_set():
                    yield VoiceEvent(kind="bargein", state=VoiceState.LISTEN)
                    break
                yield VoiceEvent(kind="audio", audio=audio_chunk)
        except asyncio.CancelledError:
            yield VoiceEvent(kind="bargein", state=VoiceState.LISTEN)
        except Exception as e:
            self._state = VoiceState.ERROR
            yield VoiceEvent(kind="error", error=f"tts: {e}", state=VoiceState.ERROR)
            return

        # After a clarification we go back to LISTEN, not IDLE, so the
        # WS client knows the next mic chunk is the user's answer.
        if clarifying:
            self._state = VoiceState.LISTEN
            yield VoiceEvent(kind="state", state=VoiceState.LISTEN)
            return

        self._state = VoiceState.IDLE
        yield VoiceEvent(kind="state", state=VoiceState.IDLE)
