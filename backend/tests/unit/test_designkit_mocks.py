"""Mock-endpoint contract tests for the designkit widgets.

These pin the JSON shape that frontend/src/lib/designkit/api.ts depends on.
If you change a seed shape here, update the corresponding TypeScript
interface in api.ts (or the live route will silently drop fields).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from vector import mocks as designkit_mocks
from vector.app import app


@pytest.fixture(autouse=True)
def _isolate_tmp_dir(tmp_path, monkeypatch):
    """Redirect /tmp-vector/mocks/ into the test's tmp_path. Each test gets
    a clean dir so we exercise the auto-generate-on-first-request path."""

    def _tmp_root() -> Path:
        d = tmp_path / "tmp-vector"
        d.mkdir(parents=True, exist_ok=True)
        return d

    monkeypatch.setattr(designkit_mocks, "tmp_root", _tmp_root)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_list_mocks_lists_all_widgets(client: TestClient):
    r = client.get("/mock/")
    assert r.status_code == 200
    body = r.json()
    assert "available" in body
    names = set(body["available"])
    # Every widget the frontend designkit knows about must have a seed.
    expected = {
        "market", "news", "tickers", "weather", "threat", "map",
        "heat", "video", "vitals", "calendar", "tasks", "agentlog",
        "voice", "clock",
    }
    assert expected.issubset(names), f"missing: {expected - names}"


def test_unknown_mock_returns_404(client: TestClient):
    r = client.get("/mock/does-not-exist")
    assert r.status_code == 404


def test_market_shape(client: TestClient):
    r = client.get("/mock/market")
    assert r.status_code == 200
    body = r.json()
    assert {"symbol", "exchange", "price", "delta_abs", "delta_pct",
            "ranges", "active_range", "stats", "candles"}.issubset(body.keys())
    assert isinstance(body["candles"], list)
    assert all({"o", "h", "l", "c"}.issubset(c.keys()) for c in body["candles"])
    assert {"open", "high", "vol", "pe"}.issubset(body["stats"].keys())


def test_news_shape(client: TestClient):
    r = client.get("/mock/news")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body["items"], list)
    assert all({"src", "headline", "age", "tag"}.issubset(n.keys()) for n in body["items"])


def test_tickers_shape(client: TestClient):
    body = client.get("/mock/tickers").json()
    assert isinstance(body["items"], list) and len(body["items"]) > 0
    for t in body["items"]:
        assert {"sym", "px", "ch", "spark"}.issubset(t.keys())
        assert isinstance(t["spark"], list)


def test_weather_shape(client: TestClient):
    body = client.get("/mock/weather").json()
    assert {"location", "condition", "temp_f", "high_f", "low_f", "feels_f", "hourly"} <= body.keys()
    assert all({"t", "temp_f"}.issubset(h.keys()) for h in body["hourly"])


def test_threat_shape(client: TestClient):
    body = client.get("/mock/threat").json()
    assert {"label", "title", "severity", "threshold", "series", "anomalies_at"} <= body.keys()
    assert isinstance(body["series"], list)


def test_map_shape(client: TestClient):
    body = client.get("/mock/map").json()
    assert {"center", "markers"} <= body.keys()
    assert {"lat", "lon"} <= body["center"].keys()
    for m in body["markers"]:
        assert {"x", "y", "color", "label"} <= m.keys()


def test_heat_shape(client: TestClient):
    body = client.get("/mock/heat").json()
    assert {"label", "title", "total_hours", "grid", "scale_min", "scale_max"} <= body.keys()
    assert isinstance(body["grid"], list) and len(body["grid"]) == 7
    assert all(len(row) == 24 for row in body["grid"])


def test_video_shape(client: TestClient):
    body = client.get("/mock/video").json()
    assert {"camera", "status", "elapsed", "resolution", "fps",
            "progress", "elapsed_short", "remaining"} <= body.keys()


def test_vitals_shape(client: TestClient):
    body = client.get("/mock/vitals").json()
    assert isinstance(body["metrics"], list) and len(body["metrics"]) == 4
    for m in body["metrics"]:
        assert {"key", "pct", "label", "sub", "heading", "meta", "color"} <= m.keys()


def test_calendar_shape(client: TestClient):
    body = client.get("/mock/calendar").json()
    assert isinstance(body["events"], list)
    for e in body["events"]:
        assert {"t", "title", "color", "live", "dur"} <= e.keys()


def test_tasks_shape(client: TestClient):
    body = client.get("/mock/tasks").json()
    assert isinstance(body["items"], list)
    for it in body["items"]:
        assert {"done", "label", "meta"} <= it.keys()


def test_agentlog_shape(client: TestClient):
    body = client.get("/mock/agentlog").json()
    assert isinstance(body["lines"], list)
    for ln in body["lines"]:
        assert {"t", "color", "text"} <= ln.keys()


def test_voice_shape(client: TestClient):
    body = client.get("/mock/voice").json()
    assert {"status", "transcript"} <= body.keys()


def test_clock_is_live(client: TestClient):
    """Clock is recomputed every request — never cached to disk."""
    body = client.get("/mock/clock").json()
    assert isinstance(body["zones"], list) and len(body["zones"]) == 4
    for z in body["zones"]:
        assert {"name", "time"} <= z.keys()
        # HH:MM
        assert len(z["time"]) == 5 and z["time"][2] == ":"


def test_seed_written_to_disk_on_first_request(client: TestClient, tmp_path):
    # First call seeds, second call reads what was written.
    a = client.get("/mock/news").json()
    seed_file = designkit_mocks.mocks_dir() / "news.json"
    assert seed_file.exists()
    on_disk = json.loads(seed_file.read_text())
    assert on_disk == a
    b = client.get("/mock/news").json()
    assert a == b


def test_clock_never_persisted_to_disk(client: TestClient):
    client.get("/mock/clock")
    assert not (designkit_mocks.mocks_dir() / "clock.json").exists()


def test_ensure_all_seeds_writes_every_file():
    designkit_mocks.ensure_all_seeds()
    written = {p.stem for p in designkit_mocks.mocks_dir().glob("*.json")}
    # clock is intentionally NOT persisted
    expected = set(designkit_mocks.all_names()) - {"clock"}
    assert expected.issubset(written)
