from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

import pytest

from vector.engine import mission as mission_eng
from vector.engine import weekly
from vector.store import connect
from vector.store import metrics as metrics_store


@pytest.fixture()
def conn(tmp_path: Path):
    c = connect(tmp_path / "v.db")
    yield c
    c.close()


def test_weekly_brief_with_no_data(conn):
    s = weekly.render_weekly(conn, now=datetime(2026, 5, 12, 16, 0))
    assert "No picks" in s.text or s.shipped == 0


def test_weekly_brief_reports_choke_points(conn):
    week_iso = weekly._week_iso(datetime(2026, 5, 12))
    mission_eng.upsert_choke_point(conn, week=week_iso, rank=1, title="EUV foundry")
    mission_eng.upsert_choke_point(conn, week=week_iso, rank=2, title="HBM supply")
    s = weekly.render_weekly(conn, now=datetime(2026, 5, 12))
    assert "EUV foundry" in s.text
    assert "HBM supply" in s.text


def test_weekly_brief_reports_us_lead_direction(conn):
    now = datetime(2026, 5, 12, 16, 0)
    week_start = weekly._week_bounds(now)[0]
    conn.execute(
        "INSERT INTO metrics(section, name, value, unit, recorded_at) VALUES(?, ?, ?, ?, ?)",
        ("mission", "us_compute_share", 0.60, "ratio", week_start - 86400),
    )
    conn.execute(
        "INSERT INTO metrics(section, name, value, unit, recorded_at) VALUES(?, ?, ?, ?, ?)",
        ("mission", "china_compute_output", 0.34, "ratio", week_start - 86400),
    )
    conn.execute(
        "INSERT INTO metrics(section, name, value, unit, recorded_at) VALUES(?, ?, ?, ?, ?)",
        ("mission", "us_compute_share", 0.63, "ratio", week_start + 3600),
    )
    conn.execute(
        "INSERT INTO metrics(section, name, value, unit, recorded_at) VALUES(?, ?, ?, ?, ?)",
        ("mission", "china_compute_output", 0.35, "ratio", week_start + 3600),
    )
    s = weekly.render_weekly(conn, now=now)
    assert "widened" in s.text or "narrowed" in s.text


def test_weekly_brief_includes_stratus_share_pct(conn):
    now = datetime(2026, 5, 12, 16, 0)
    conn.execute(
        "INSERT INTO metrics(section, name, value, unit, recorded_at) VALUES(?, ?, ?, ?, ?)",
        ("mission", "stratus_share_us_mil", 0.012, "ratio", time.time()),
    )
    s = weekly.render_weekly(conn, now=now)
    assert "Stratus" in s.text
    assert "%" in s.text
