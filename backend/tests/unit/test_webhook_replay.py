from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from vector.store import connect
from vector.webhooks.linear import (
    MAX_CLOCK_SKEW_S,
    _parse_iso,
    handle_linear_event,
)


def _iso_at(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _payload(created_at: str, **overrides) -> dict:
    base = {
        "action": "update",
        "type": "Issue",
        "createdAt": created_at,
        "data": {
            "id": "lin-issue-1",
            "title": "Ship",
            "priority": 1,
            "estimate": 5,
            "state": {"name": "In Progress"},
        },
    }
    base.update(overrides)
    return base


@pytest.fixture()
def conn(tmp_path: Path):
    c = connect(tmp_path / "v.db")
    yield c
    c.close()


def test_fresh_delivery_accepted(conn):
    now = time.time()
    out = handle_linear_event(conn, _payload(_iso_at(now)), now=now)
    assert out.get("ok") is True


def test_stale_delivery_rejected(conn):
    now = time.time()
    stale = _iso_at(now - MAX_CLOCK_SKEW_S - 1)
    out = handle_linear_event(conn, _payload(stale), now=now)
    assert out.get("ignored") is True
    assert "stale" in out["reason"]


def test_future_skew_rejected(conn):
    now = time.time()
    future = _iso_at(now + MAX_CLOCK_SKEW_S + 1)
    out = handle_linear_event(conn, _payload(future), now=now)
    assert out.get("ignored") is True


def test_missing_created_at_rejected(conn):
    out = handle_linear_event(conn, _payload(""))
    assert out.get("ignored") is True
    assert "createdAt" in out["reason"]


def test_bad_iso_rejected(conn):
    out = handle_linear_event(conn, _payload("not-a-date"))
    assert out.get("ignored") is True


def test_parse_iso_handles_z_suffix():
    ts = _parse_iso("2026-05-12T05:00:00Z")
    assert ts is not None


def test_parse_iso_handles_naive_falls_back_to_utc():
    ts = _parse_iso("2026-05-12T05:00:00")
    assert ts is not None


def test_parse_iso_handles_offset():
    ts = _parse_iso("2026-05-12T05:00:00+02:00")
    assert ts is not None
