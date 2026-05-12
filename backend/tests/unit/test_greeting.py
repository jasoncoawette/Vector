from __future__ import annotations

from datetime import datetime

from fastapi.testclient import TestClient

from vector.app import _greeting_for, app


def test_greeting_endpoint_returns_text_for_jason():
    client = TestClient(app)
    r = client.get("/voice/greeting")
    assert r.status_code == 200
    body = r.json()
    assert body["user"] == "Jason"
    assert "Jason" in body["text"]


def test_morning_phrase():
    text = _greeting_for(datetime(2026, 5, 12, 5, 0))
    assert text.startswith("Good morning")


def test_afternoon_phrase():
    text = _greeting_for(datetime(2026, 5, 12, 13, 0))
    assert text.startswith("Good afternoon")


def test_evening_phrase():
    text = _greeting_for(datetime(2026, 5, 12, 21, 0))
    assert text.startswith("Good evening")
