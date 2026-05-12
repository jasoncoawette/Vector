from __future__ import annotations

import pytest

from vector.voice.wake import FakeWakeDetector, PicovoiceWakeDetector


def test_fake_returns_scripted_matches():
    d = FakeWakeDetector(matches=[False, False, True, False])
    assert d.process(b"\x00\x00") is False
    assert d.process(b"\x00\x00") is False
    assert d.process(b"\x00\x00") is True
    assert d.process(b"\x00\x00") is False


def test_fake_empty_returns_false():
    d = FakeWakeDetector(matches=[])
    assert d.process(b"\x00\x00") is False


def test_fake_close_blocks_processing():
    d = FakeWakeDetector(matches=[True])
    d.close()
    assert d.process(b"\x00\x00") is False


def test_picovoice_rejects_empty_inputs():
    with pytest.raises(ValueError):
        PicovoiceWakeDetector(access_key="", keyword_path="x.ppn")
    with pytest.raises(ValueError):
        PicovoiceWakeDetector(access_key="k", keyword_path="")
