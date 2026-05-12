from __future__ import annotations

import time
from pathlib import Path

import pytest

from vector.store import connect
from vector.store import metrics as metrics_store


@pytest.fixture()
def conn(tmp_path: Path):
    c = connect(tmp_path / "v.db")
    yield c
    c.close()


def test_record_rejects_unknown_section(conn):
    with pytest.raises(ValueError):
        metrics_store.record(conn, section="boeing", name="x", value=1.0)


def test_record_rejects_empty_name(conn):
    with pytest.raises(ValueError):
        metrics_store.record(conn, section="stratus", name="  ", value=1.0)


def test_latest_returns_only_most_recent(conn):
    metrics_store.record(conn, section="stratus", name="revenue", value=1000)
    time.sleep(0.01)
    metrics_store.record(conn, section="stratus", name="revenue", value=2000)
    out = metrics_store.latest(conn, "stratus")
    assert len(out) == 1
    assert out[0].value == 2000


def test_latest_groups_by_name(conn):
    metrics_store.record(conn, section="stratus", name="revenue", value=1000)
    metrics_store.record(conn, section="stratus", name="lois", value=3)
    out = metrics_store.latest(conn, "stratus")
    names = {p.name for p in out}
    assert names == {"revenue", "lois"}


def test_history_is_chronological_desc(conn):
    metrics_store.record(conn, section="personal", name="sleep", value=7)
    time.sleep(0.01)
    metrics_store.record(conn, section="personal", name="sleep", value=6)
    out = metrics_store.history(conn, "personal", "sleep")
    assert [p.value for p in out] == [6, 7]


def test_stale_check_uses_section_horizon(conn):
    point = metrics_store.MetricPoint(
        section="mission",
        name="us_share",
        value=0.5,
        unit=None,
        recorded_at=time.time() - 10 * 24 * 3600,
    )
    assert metrics_store.is_stale(point) is True

    fresh = metrics_store.MetricPoint(
        section="mission",
        name="us_share",
        value=0.5,
        unit=None,
        recorded_at=time.time() - 60,
    )
    assert metrics_store.is_stale(fresh) is False
