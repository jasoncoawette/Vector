"""Designkit mock endpoints. Each widget that doesn't have a real backing
service (Market, News, Tickers, Weather, Threat, Map, Heat, Video, Clock,
Vitals, Calendar, Tasks) is served deterministic mock data from
/tmp-vector/mocks/<name>.json. Files are auto-generated on first request
if missing. The /tmp-vector directory is gitignored — safe scratch space.

Real data flows in once the user wires API keys: just delete the JSON file
and replace this router's endpoint with the real impl, or proxy to it.
"""
from __future__ import annotations

import json
import math
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from fastapi import APIRouter, HTTPException, status

router = APIRouter(prefix="/mock", tags=["mock"])


def tmp_root() -> Path:
    """Repo-root /tmp-vector/. Created on demand, never checked in.
    Three parents up: backend/vector/mocks.py -> backend/vector -> backend -> repo."""
    here = Path(__file__).resolve()
    root = here.parent.parent.parent / "tmp-vector"
    root.mkdir(parents=True, exist_ok=True)
    return root


def mocks_dir() -> Path:
    d = tmp_root() / "mocks"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _load_or_seed(name: str, seed: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    path = mocks_dir() / f"{name}.json"
    if not path.exists():
        path.write_text(json.dumps(seed(), indent=2))
    return json.loads(path.read_text())


def _seed_market() -> dict[str, Any]:
    rng = random.Random(42)
    candles: list[dict[str, float]] = []
    for i in range(22):
        base = 100 + i * 1.4 + math.sin(i * 0.6) * 5
        o = base + (rng.random() - 0.5) * 1.5
        c = o + (rng.random() - 0.45) * 3.5
        h = max(o, c) + rng.random() * 1.6
        lo = min(o, c) - rng.random() * 1.6
        candles.append({"o": o, "h": h, "l": lo, "c": c})
    return {
        "symbol": "NVDA",
        "exchange": "NASDAQ",
        "price": 1142.08,
        "delta_abs": 18.42,
        "delta_pct": 1.64,
        "ranges": ["1D", "1W", "1M", "1Y"],
        "active_range": "1M",
        "stats": {"open": 1124.10, "high": 1148.92, "vol": "38.4M", "pe": 62.1},
        "candles": candles,
    }


def _seed_news() -> dict[str, Any]:
    return {
        "items": [
            {"src": "REUTERS", "headline": "Fed signals pause on rate cuts pending CPI", "age": "4m", "tag": "MARKETS"},
            {"src": "BLOOMBERG", "headline": "Nvidia ships Blackwell ahead of schedule", "age": "22m", "tag": "TECH"},
            {"src": "AP", "headline": "Senate advances AI safety reporting bill", "age": "1h", "tag": "POLICY"},
            {"src": "FT", "headline": "Container freight rates fall 8% week-over-week", "age": "3h", "tag": "GLOBAL"},
        ]
    }


def _seed_tickers() -> dict[str, Any]:
    return {
        "items": [
            {"sym": "SPX", "px": "5,872.4", "ch": 0.42, "spark": [12, 14, 16, 15, 18, 17, 19, 22, 21, 24, 23, 26]},
            {"sym": "NDX", "px": "20,114", "ch": 0.81, "spark": [22, 20, 24, 26, 25, 28, 27, 30, 32, 31, 34, 38]},
            {"sym": "BTC", "px": "95,214", "ch": -1.24, "spark": [28, 30, 29, 27, 26, 28, 24, 22, 23, 21, 19, 20]},
            {"sym": "ETH", "px": "3,284", "ch": 0.18, "spark": [12, 13, 12, 14, 15, 14, 16, 15, 17, 16, 18, 17]},
            {"sym": "VEC", "px": "142.86", "ch": 2.41, "spark": [8, 10, 12, 11, 14, 17, 16, 19, 22, 24, 28, 30]},
            {"sym": "DXY", "px": "104.21", "ch": -0.12, "spark": [20, 21, 21, 20, 19, 20, 19, 18, 19, 18, 17, 18]},
        ]
    }


def _seed_weather() -> dict[str, Any]:
    return {
        "location": "SAN FRANCISCO",
        "condition": "CLEAR",
        "temp_f": 62,
        "high_f": 68,
        "low_f": 54,
        "feels_f": 60,
        "hourly": [
            {"t": "NOW", "temp_f": 62},
            {"t": "11a", "temp_f": 64},
            {"t": "1p", "temp_f": 67},
            {"t": "3p", "temp_f": 67},
            {"t": "5p", "temp_f": 64},
            {"t": "7p", "temp_f": 59},
        ],
    }


def _seed_threat() -> dict[str, Any]:
    rng = random.Random(7)
    series = [
        0.2 + math.sin(i * 0.4 + 1) * 0.15 + rng.random() * 0.4 + (0.5 if i == 28 else 0) + (0.7 if i == 35 else 0)
        for i in range(40)
    ]
    return {
        "label": "SIGNAL · LIVE",
        "title": "2 anomalies · last 4h",
        "severity": "ELEVATED",
        "threshold": 0.65,
        "series": series,
        "anomalies_at": ["21:14", "21:38"],
    }


def _seed_map() -> dict[str, Any]:
    return {
        "center": {"lat": 37.7749, "lon": -122.4194},
        "markers": [
            {"x": 120, "y": 90, "color": "var(--vec)", "label": "HOME"},
            {"x": 200, "y": 70, "color": "var(--ok)", "label": "OFFICE"},
            {"x": 260, "y": 110, "color": "var(--warn)", "label": "GYM"},
        ],
    }


def _seed_heat() -> dict[str, Any]:
    rng = random.Random(11)
    grid = [[round(rng.random(), 3) for _ in range(24)] for _ in range(7)]
    return {
        "label": "ACTIVITY · 7×24",
        "title": "Deep-work density",
        "total_hours": 52,
        "grid": grid,
        "scale_min": 0,
        "scale_max": 8,
    }


def _seed_video() -> dict[str, Any]:
    return {
        "camera": "CAM-04",
        "status": "LIVE",
        "elapsed": "04:22:18",
        "resolution": "1080p",
        "fps": 30,
        "progress": 0.38,
        "elapsed_short": "01:42",
        "remaining": "-02:48",
    }


def _seed_vitals() -> dict[str, Any]:
    return {
        "metrics": [
            {"key": "hr", "pct": 68, "label": "62", "sub": "HR", "heading": "RESTING", "meta": "-3 vs avg", "color": "var(--vec)"},
            {"key": "hrv", "pct": 82, "label": "82", "sub": "HRV", "heading": "RECOVERY", "meta": "+6 vs 7d", "color": "var(--vec)"},
            {"key": "strain", "pct": 48, "label": "48", "sub": "STRAIN", "heading": "EXERTION", "meta": "nominal", "color": "var(--warn)"},
            {"key": "sleep", "pct": 94, "label": "6.4h", "sub": "SLEEP", "heading": "EFFICIENCY", "meta": "94%", "color": "var(--ok)"},
        ]
    }


def _seed_calendar() -> dict[str, Any]:
    return {
        "events": [
            {"t": "09:00", "title": "Standup · Platform", "color": "var(--vec)", "live": False, "dur": "15m"},
            {"t": "10:30", "title": "1:1 with Mira", "color": "var(--gold)", "live": False, "dur": "30m"},
            {"t": "13:00", "title": "Series B demo · v7", "color": "var(--mag)", "live": True, "dur": "45m"},
            {"t": "15:30", "title": "Deep work · pricing", "color": "var(--ok)", "live": False, "dur": "2h"},
            {"t": "19:00", "title": "Dinner · Saburo", "color": "var(--ink-2)", "live": False, "dur": "-"},
        ]
    }


def _seed_tasks() -> dict[str, Any]:
    return {
        "items": [
            {"done": True, "label": "Send pricing v4 to legal", "meta": "Drafted by Vector"},
            {"done": False, "label": "Review Anya's onboarding", "meta": "Due 17:00", "flag": "warn"},
            {"done": False, "label": "Approve Q2 spend", "meta": "3 line items"},
            {"done": False, "label": "Reply to investor intro", "meta": "2 days idle", "flag": "crit"},
        ]
    }


def _seed_agentlog() -> dict[str, Any]:
    return {
        "lines": [
            {"t": "21:14:08", "color": "var(--ink-3)", "text": "Indexed 3 PDFs from inbox"},
            {"t": "21:14:32", "color": "var(--ink-3)", "text": "Cross-referenced with Vault.notes/Q3"},
            {"t": "21:14:41", "color": "var(--vec)", "text": "Drafted reply to Mira (487 tokens)"},
            {"t": "21:15:02", "color": "var(--ok)", "text": "Confirmed table at Saburo · 7pm"},
            {"t": "21:15:18", "color": "var(--ink-3)", "text": "Watching: GitHub auth-service, AWS billing"},
            {"t": "21:15:44", "color": "var(--warn)", "text": "Anomaly: us-west-2 cost +14% vs 7d avg"},
            {"t": "21:16:02", "color": "var(--ink-3)", "text": "Context window: 412K / 1M"},
            {"t": "21:16:19", "color": "var(--mag)", "text": "Vault sync · 24 items · 1.4s"},
        ]
    }


def _seed_voice() -> dict[str, Any]:
    return {
        "status": "LISTENING · 0:14",
        "transcript": "remind me to follow up with the architect about the kitchen...",
    }


def _seed_clock() -> dict[str, Any]:
    """Server-driven world clock. Computed live so it always reflects 'now'
    but stored as a snapshot fixture if no Internet/timezone DB is available."""
    now_utc = datetime.now(timezone.utc)
    offsets = [("NEW YORK", -4), ("LONDON", 1), ("TOKYO", 9), ("SAN FRANCISCO", -7)]
    zones = []
    for name, offset_hours in offsets:
        local = now_utc + timedelta(hours=offset_hours)
        zones.append({"name": name, "time": local.strftime("%H:%M")})
    return {"zones": zones}


_SEEDS: dict[str, Callable[[], dict[str, Any]]] = {
    "market": _seed_market,
    "news": _seed_news,
    "tickers": _seed_tickers,
    "weather": _seed_weather,
    "threat": _seed_threat,
    "map": _seed_map,
    "heat": _seed_heat,
    "video": _seed_video,
    "vitals": _seed_vitals,
    "calendar": _seed_calendar,
    "tasks": _seed_tasks,
    "agentlog": _seed_agentlog,
    "voice": _seed_voice,
    "clock": _seed_clock,
}


def all_names() -> list[str]:
    return sorted(_SEEDS.keys())


def ensure_all_seeds() -> None:
    """Eagerly write every missing seed file. Called from app startup so a
    fresh checkout has /tmp-vector/mocks/*.json ready before any request.
    Clock is excluded — it's recomputed live on every request."""
    for name, seed in _SEEDS.items():
        if name == "clock":
            continue
        _load_or_seed(name, seed)


@router.get("/")
def list_mocks() -> dict:
    return {"available": all_names(), "tmp_dir": str(mocks_dir())}


@router.get("/clock")
def get_clock() -> dict:
    # Clock is recomputed every request — we never cache the JSON.
    return _seed_clock()


@router.get("/{name}")
def get_mock(name: str) -> dict:
    seed = _SEEDS.get(name)
    if seed is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"unknown mock '{name}'")
    return _load_or_seed(name, seed)
