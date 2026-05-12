from __future__ import annotations

from vector.prompts import (
    CLARIFICATION_RULE,
    CLARIFY_MARKER,
    NO_HALLUCINATION_RULE,
    SYSTEM_PROMPTS,
    VERIFIER_SYSTEM,
    VOICE_BRAIN_SYSTEM,
    compose,
    needs_clarification,
    strip_clarify_marker,
)


def test_compose_drops_empties_and_joins_with_blank_lines():
    out = compose("first", "", "second")
    assert "first" in out
    assert "second" in out
    assert "\n\n" in out
    assert "  " not in out  # no double-spaces from empties


def test_compose_handles_all_empty():
    assert compose("", "  ") == ""


def test_voice_brain_includes_clarification_rule():
    assert CLARIFICATION_RULE in VOICE_BRAIN_SYSTEM
    assert NO_HALLUCINATION_RULE in VOICE_BRAIN_SYSTEM


def test_voice_brain_mentions_one_or_two_sentences():
    # Voice-length rule should be in the composed prompt.
    assert "one or two" in VOICE_BRAIN_SYSTEM.lower()


def test_every_agent_type_has_a_prompt():
    for agent_type in ("code", "research", "writer", "tester", "security"):
        assert agent_type in SYSTEM_PROMPTS
        assert NO_HALLUCINATION_RULE in SYSTEM_PROMPTS[agent_type]


def test_security_agent_inherits_no_hallucination_and_citation():
    p = SYSTEM_PROMPTS["security"]
    assert "OWASP" in p
    assert "ITAR" in p
    assert NO_HALLUCINATION_RULE in p


def test_verifier_prompt_still_demands_json():
    assert "JSON" in VERIFIER_SYSTEM
    assert "success" in VERIFIER_SYSTEM


def test_needs_clarification_detects_marker():
    assert needs_clarification(f"{CLARIFY_MARKER} which sprint?")
    assert not needs_clarification("here is your answer")


def test_strip_clarify_marker_returns_clean_text():
    assert strip_clarify_marker(f"{CLARIFY_MARKER} which sprint?") == "which sprint?"
    assert strip_clarify_marker("no marker here") == "no marker here"
