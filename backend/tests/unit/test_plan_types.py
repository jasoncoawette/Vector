from __future__ import annotations

import pytest

from vector.plans import Plan, Step, make_plan_id
from vector.plans.schema import PlanIn, StepIn, build_plan
from vector.plans.types import PLACEHOLDER_RE, PlanValidationError, validate


def _step(id_: int, **kw) -> Step:
    base = {
        "agent": "research",
        "prompt": "do thing",
        "depends_on": (),
    }
    base.update(kw)
    return Step(id=id_, **base)


def test_simple_linear_plan_validates():
    plan = Plan(
        id="p1",
        goal="ship",
        steps=(
            _step(1),
            _step(2, depends_on=(1,), prompt="use {{step_1.output}}"),
        ),
    )
    validate(plan)  # no exception


def test_duplicate_ids_rejected():
    plan = Plan(id="p", goal="g", steps=(_step(1), _step(1)))
    with pytest.raises(PlanValidationError, match="unique"):
        validate(plan)


def test_dep_on_unknown_step_rejected():
    plan = Plan(id="p", goal="g", steps=(_step(1, depends_on=(99,)),))
    with pytest.raises(PlanValidationError, match="unknown"):
        validate(plan)


def test_self_dependency_rejected():
    plan = Plan(id="p", goal="g", steps=(_step(1, depends_on=(1,)),))
    with pytest.raises(PlanValidationError, match="itself"):
        validate(plan)


def test_cycle_rejected():
    plan = Plan(
        id="p",
        goal="g",
        steps=(
            _step(1, depends_on=(2,)),
            _step(2, depends_on=(1,)),
        ),
    )
    with pytest.raises(PlanValidationError, match="cycle"):
        validate(plan)


def test_long_cycle_rejected():
    plan = Plan(
        id="p",
        goal="g",
        steps=(
            _step(1, depends_on=(3,)),
            _step(2, depends_on=(1,)),
            _step(3, depends_on=(2,)),
        ),
    )
    with pytest.raises(PlanValidationError, match="cycle"):
        validate(plan)


def test_placeholder_must_reference_declared_dep():
    plan = Plan(
        id="p",
        goal="g",
        steps=(
            _step(1),
            _step(2, prompt="based on {{step_1.output}}"),  # no depends_on=1
        ),
    )
    with pytest.raises(PlanValidationError, match="does not declare"):
        validate(plan)


def test_placeholder_pattern_matches_common_forms():
    cases = [
        "{{step_1.output}}",
        "{{ step_2.output }}",
        "see {{step_3.output}} below",
    ]
    for s in cases:
        m = PLACEHOLDER_RE.search(s)
        assert m is not None


def test_make_plan_id_unique():
    seen = {make_plan_id() for _ in range(50)}
    assert len(seen) == 50


def test_build_plan_from_pydantic_payload_round_trip():
    payload = PlanIn(
        goal="research and write the AFWERX SBIR application",
        steps=[
            StepIn(id=1, agent="research", prompt="find current AFWERX SBIR phases"),
            StepIn(
                id=2,
                agent="writer",
                prompt="draft an application based on {{step_1.output}}",
                depends_on=[1],
                success_criteria="3 pages, action-first, cites the phase number",
            ),
        ],
    )
    plan = build_plan(payload)
    assert plan.goal.startswith("research")
    assert len(plan.steps) == 2
    assert plan.steps[1].depends_on == (1,)
    assert plan.steps[1].success_criteria is not None


def test_build_plan_rejects_bad_dag():
    payload = PlanIn(
        goal="g",
        steps=[
            StepIn(id=1, agent="code", prompt="x", depends_on=[2]),
            StepIn(id=2, agent="code", prompt="y", depends_on=[1]),
        ],
    )
    with pytest.raises(PlanValidationError):
        build_plan(payload)


def test_plan_to_dict_round_trips_fields():
    plan = Plan(
        id="p1",
        goal="ship",
        steps=(_step(1, prompt="hello"),),
    )
    d = plan.to_dict()
    assert d["id"] == "p1"
    assert d["goal"] == "ship"
    assert d["steps"][0]["agent"] == "research"
