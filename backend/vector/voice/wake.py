from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class WakeDetector(Protocol):
    """Detects a wake word in a PCM frame. Returns True if matched."""

    @property
    def sample_rate(self) -> int: ...
    @property
    def frame_length(self) -> int: ...
    def process(self, frame: bytes) -> bool: ...
    def close(self) -> None: ...


@dataclass
class FakeWakeDetector:
    """Scripted detector for tests."""

    matches: list[bool]
    sample_rate: int = 16_000
    frame_length: int = 512
    closed: bool = False

    def process(self, frame: bytes) -> bool:
        if self.closed:
            return False
        if not self.matches:
            return False
        return self.matches.pop(0)

    def close(self) -> None:
        self.closed = True


class PicovoiceWakeDetector:
    """Real wake-word detector backed by Picovoice Porcupine.

    pvporcupine is loaded lazily so tests don't need it.
    `keyword_path` points at a `.ppn` file for the "Vector" wake word.
    """

    def __init__(self, access_key: str, keyword_path: str) -> None:
        if not access_key:
            raise ValueError("Picovoice access key required")
        if not keyword_path:
            raise ValueError("keyword_path required")
        self._access_key = access_key
        self._keyword_path = keyword_path
        self._handle = None

    def _load(self) -> None:
        if self._handle is not None:
            return
        import pvporcupine

        self._handle = pvporcupine.create(
            access_key=self._access_key,
            keyword_paths=[self._keyword_path],
        )

    @property
    def sample_rate(self) -> int:
        self._load()
        return int(self._handle.sample_rate)

    @property
    def frame_length(self) -> int:
        self._load()
        return int(self._handle.frame_length)

    def process(self, frame: bytes) -> bool:
        import struct

        self._load()
        pcm = struct.unpack_from(f"{len(frame) // 2}h", frame)
        return self._handle.process(pcm) >= 0

    def close(self) -> None:
        if self._handle is not None:
            self._handle.delete()
            self._handle = None
