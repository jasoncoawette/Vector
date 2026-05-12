from __future__ import annotations

import json
from pathlib import Path

import pytest

from vector.engine import picker, review
from vector.store import connect
from vector.store import tasks as tasks_repo


@pytest.fixture()
def conn(tmp_path: Path):
    c = connect(tmp_path / "v.db")
    yield c
    c.close()


def _seed_day(conn) -> dict[str, int]:
    ids = {
        "a": tasks_repo.upsert(
            conn,
            external_id="A",
            title="Ship CLI",
            source="linear",
            tag="outcome",
            mission="stratus",
            priority=1,
        ),
        "b": tasks_repo.upsert(
            conn,
            external_id="B",
            title="LOI follow-up",
            source="linear",
            tag="outcome",
            mission="stratus",
            priority=2,
        ),
        "c": tasks_repo.upsert(
            conn,
            external_id="C",
            title="Paperwork",
            source="linear",
            tag="process",
            mission="stratus",
            priority=3,
        ),
    }
    picks = picker.pick_top(conn, day="2026-05-12")
    picker.log_picks(conn, "2026-05-12", picks)
    return ids


def test_review_marks_shipped(conn):
    ids = _seed_day(conn)
    r = review.record_review(conn, day="2026-05-12", shipped_ids=[ids["a"]])
    assert ids["a"] in r.shipped_ids
    assert tasks_repo.get(conn, ids["a"]).status == "shipped"


def test_review_filters_unknown_shipped_ids(conn):
    _seed_day(conn)
    r = review.record_review(conn, day="2026-05-12", shipped_ids=[99999])
    assert r.shipped_ids == []


def test_review_upsert_overwrites_same_day(conn):
    ids = _seed_day(conn)
    review.record_review(conn, day="2026-05-12", shipped_ids=[ids["a"]])
    review.record_review(conn, day="2026-05-12", shipped_ids=[ids["a"], ids["b"]])
    row = conn.execute(
        "SELECT shipped_ids FROM reviews WHERE day=?", ("2026-05-12",)
    ).fetchone()
    assert sorted(json.loads(row["shipped_ids"])) == sorted([ids["a"], ids["b"]])


def test_render_review_mentions_titles(conn):
    ids = _seed_day(conn)
    r = review.record_review(conn, day="2026-05-12", shipped_ids=[ids["a"]])
    text = review.render_review(r, conn)
    assert "Ship CLI" in text
    assert "Shipped 1 of" in text


def test_render_empty_review(conn):
    r = review.record_review(conn, day="2026-01-01", shipped_ids=[])
    text = review.render_review(r, conn)
    assert "No picks" in text
