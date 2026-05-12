from __future__ import annotations

import pytest

from vector.agents.verifier import ClaudeVerifier, FakeVerifier, Verdict, _extract_json
from vector.voice.brain import BrainReply, FakeBrain


def test_extract_json_handles_clean_payload():
    data = _extract_json('{"success": true, "reason": "ok"}')
    assert data["success"] is True


def test_extract_json_handles_leading_chatter():
    data = _extract_json('Sure! Here is the verdict: {"success": false, "reason": "x"}')
    assert data["success"] is False


def test_extract_json_handles_code_fence():
    text = '```json\n{"success": true, "reason": "ok"}\n```'
    data = _extract_json(text)
    assert data["success"] is True


def test_extract_json_rejects_no_object():
    with pytest.raises(ValueError):
        _extract_json("no json here")


async def test_claude_verifier_passes_through_success():
    def factory(_t):
        return FakeBrain(
            [BrainReply(text='{"success": true, "reason": "matches contract"}', final=True, cost_usd=0.001)]
        )

    v = ClaudeVerifier(brain_factory=factory)
    verdict = await v.check("ship the CLI", "shipped the CLI")
    assert verdict.success is True
    assert verdict.reason == "matches contract"
    assert verdict.cost_usd == pytest.approx(0.001)


async def test_claude_verifier_passes_through_failure():
    def factory(_t):
        return FakeBrain(
            [BrainReply(text='{"success": false, "reason": "no CLI binary in output"}', final=True)]
        )

    v = ClaudeVerifier(brain_factory=factory)
    verdict = await v.check("ship the CLI", "draft of the README")
    assert verdict.success is False
    assert "no CLI binary" in verdict.reason


async def test_claude_verifier_fails_closed_on_bad_json():
    def factory(_t):
        return FakeBrain([BrainReply(text="the output looks fine to me", final=True)])

    v = ClaudeVerifier(brain_factory=factory)
    verdict = await v.check("criterion", "out")
    assert verdict.success is False
    assert "parse" in verdict.reason


async def test_claude_verifier_fails_closed_on_missing_key():
    def factory(_t):
        return FakeBrain([BrainReply(text='{"only_reason": "I forgot success"}', final=True)])

    v = ClaudeVerifier(brain_factory=factory)
    verdict = await v.check("c", "o")
    assert verdict.success is False


async def test_fake_verifier_pops_in_order():
    v = FakeVerifier([Verdict(success=False, reason="r1"), Verdict(success=True, reason="r2")])
    a = await v.check("c", "o")
    b = await v.check("c", "o")
    assert (a.success, b.success) == (False, True)


async def test_fake_verifier_defaults_to_pass_when_empty():
    v = FakeVerifier([])
    verdict = await v.check("c", "o")
    assert verdict.success is True
