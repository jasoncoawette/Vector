from __future__ import annotations

import pytest

from vector.voice.routing import (
    THRESH_HARD,
    THRESH_SIMPLE,
    Tier,
    complexity_score,
    heuristic_route,
)


def test_simple_prompt_routes_to_haiku():
    d = heuristic_route("show me today's picks")
    assert d.tier == Tier.HAIKU


def test_medium_prompt_routes_to_sonnet():
    d = heuristic_route("implement the email summarizer and write tests for it")
    assert d.tier == Tier.SONNET


def test_architecture_prompt_routes_to_opus():
    long_arch = (
        "Draft a threat model and architecture decision record for the new ITAR audit pipeline. "
        "Document the tradeoffs and migration plan. Cover security, schema, and refactor risks."
    )
    d = heuristic_route(long_arch)
    assert d.tier == Tier.OPUS


def test_code_agent_pushes_score_up():
    plain, _ = complexity_score("write a helper function")
    coded, _ = complexity_score("write a helper function", agent_type="code")
    assert coded > plain


def test_security_agent_pushes_score_up():
    plain, _ = complexity_score("check the input")
    sec, _ = complexity_score("check the input", agent_type="security")
    assert sec > plain


def test_score_clamped_to_unit_interval():
    score, _ = complexity_score("threat model architecture security refactor schema migration audit incident" * 5)
    assert 0.0 <= score <= 1.0


def test_thresholds_stay_ordered():
    assert THRESH_SIMPLE < THRESH_HARD


def test_features_returned_for_audit():
    _, feats = complexity_score("rename the file please")
    assert "simple_kw" in feats
    assert feats["simple_kw"] > 0


def test_code_fence_detection():
    _, feats = complexity_score("here is the function:\n```python\ndef f():\n    pass\n```")
    assert feats["has_code"] == 1.0
