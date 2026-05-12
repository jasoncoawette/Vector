from __future__ import annotations

from pathlib import Path

import pytest

from vector.engine import picker
from vector.store import connect
from vector.store import tasks as tasks_repo


@pytest.fixture()
def conn(tmp_path: Path):
    c = connect(tmp_path / "v.db")
    yield c
    c.close()


def _seed(conn) -> dict[str, int]:
    return {
        "ship_cli": tasks_repo.upsert(
            conn,
            external_id="A",
            title="Ship Stratus CLI",
            source="linear",
            tag="outcome",
            mission="stratus",
            priority=1,
        ),
        "boeing_meeting": tasks_repo.upsert(
            conn,
            external_id="B",
            title="Boeing standup",
            source="linear",
            tag="process",
            mission="boeing",
            priority=2,
        ),
        "stratus_admin": tasks_repo.upsert(
            conn,
            external_id="C",
            title="File Stratus paperwork",
            source="linear",
            tag="process",
            mission="stratus",
            priority=3,
        ),
        "outcome_low_pri": tasks_repo.upsert(
            conn,
            external_id="D",
            title="LOI follow-up",
            source="linear",
            tag="outcome",
            mission="stratus",
            priority=2,
        ),
    }


def test_picks_three(conn):
    _seed(conn)
    picks = picker.pick_top(conn, day="2026-05-12")
    assert len(picks) == 3


def test_outcome_beats_process_at_same_priority(conn):
    ids = _seed(conn)
    picks = picker.pick_top(conn, day="2026-05-12")
    top_ids = [p.task.id for p in picks]
    assert ids["ship_cli"] in top_ids
    assert ids["outcome_low_pri"] in top_ids


def test_boeing_is_deferred_below_stratus(conn):
    ids = _seed(conn)
    picks = picker.pick_top(conn, day="2026-05-12")
    top_ids = [p.task.id for p in picks]
    assert ids["boeing_meeting"] not in top_ids


def test_calendar_today_boosts(conn):
    _seed(conn)
    picks_plain = picker.pick_top(conn, day="2026-05-12")
    picks_cal = picker.pick_top(conn, day="2026-05-12", calendar_today_ids={"C"})
    assert picks_cal[0].score >= picks_plain[0].score


def test_log_picks_replaces_same_day(conn):
    _seed(conn)
    picks = picker.pick_top(conn, day="2026-05-12")
    picker.log_picks(conn, "2026-05-12", picks)
    picker.log_picks(conn, "2026-05-12", picks[:1])
    n = conn.execute("SELECT COUNT(*) AS n FROM picks WHERE day=?", ("2026-05-12",)).fetchone()["n"]
    assert n == 1


def test_override_shifts_weights(conn):
    ids = _seed(conn)
    before = picker.load_weights(conn)
    picker.record_override(
        conn,
        day="2026-05-12",
        removed_task_id=ids["stratus_admin"],
        added_task_id=ids["outcome_low_pri"],
    )
    after = picker.load_weights(conn)
    assert after["outcome"] > before["outcome"]


def test_override_logged(conn):
    ids = _seed(conn)
    picker.record_override(
        conn,
        day="2026-05-12",
        removed_task_id=ids["stratus_admin"],
        added_task_id=ids["outcome_low_pri"],
    )
    n = conn.execute("SELECT COUNT(*) AS n FROM overrides").fetchone()["n"]
    assert n == 1


def test_reasons_are_human_readable(conn):
    _seed(conn)
    picks = picker.pick_top(conn, day="2026-05-12")
    for p in picks:
        assert p.task.title in p.reason
        assert len(p.reason) < 200
