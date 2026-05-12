from __future__ import annotations

from pathlib import Path

import pytest

from vector.engine import mission
from vector.store import connect


@pytest.fixture()
def conn(tmp_path: Path):
    c = connect(tmp_path / "v.db")
    yield c
    c.close()


def test_seed_writes_three_baselines(conn):
    written = mission.seed_mission_baseline(conn)
    assert set(written) == set(mission.MISSION_METRIC_NAMES)


def test_seed_is_idempotent(conn):
    mission.seed_mission_baseline(conn)
    again = mission.seed_mission_baseline(conn)
    assert again == {}


def test_choke_point_upsert(conn):
    a = mission.upsert_choke_point(conn, week="2026-W19", rank=1, title="EUV foundry")
    b = mission.upsert_choke_point(
        conn, week="2026-W19", rank=1, title="EUV foundry (updated)", note="ASML"
    )
    assert a == b
    out = mission.list_choke_points(conn, "2026-W19")
    assert out[0].title == "EUV foundry (updated)"
    assert out[0].note == "ASML"


def test_choke_point_rejects_bad_rank(conn):
    with pytest.raises(ValueError):
        mission.upsert_choke_point(conn, week="2026-W19", rank=4, title="x")
    with pytest.raises(ValueError):
        mission.upsert_choke_point(conn, week="2026-W19", rank=0, title="x")


def test_choke_point_rejects_empty_title(conn):
    with pytest.raises(ValueError):
        mission.upsert_choke_point(conn, week="2026-W19", rank=1, title=" ")


def test_choke_points_sorted_by_rank(conn):
    mission.upsert_choke_point(conn, week="2026-W19", rank=3, title="C")
    mission.upsert_choke_point(conn, week="2026-W19", rank=1, title="A")
    mission.upsert_choke_point(conn, week="2026-W19", rank=2, title="B")
    out = mission.list_choke_points(conn, "2026-W19")
    assert [p.title for p in out] == ["A", "B", "C"]
