from __future__ import annotations

from typing import Any

import pytest

from vector.tools.errors import ToolDenied
from vector.tools.maps import (
    MapsClient,
    _coerce_directions,
    _coerce_geocode,
    _coerce_latlng,
    _coerce_places,
)


# ---- coercion helpers (pure functions, no network) ----


def test_geocode_ok_payload():
    out = _coerce_geocode(
        {
            "status": "OK",
            "results": [
                {
                    "formatted_address": "Renton, WA",
                    "geometry": {"location": {"lat": 47.5, "lng": -122.2}},
                    "place_id": "x",
                    "types": ["locality"],
                }
            ],
        }
    )
    assert out == {
        "ok": True,
        "address": "Renton, WA",
        "lat": 47.5,
        "lng": -122.2,
        "place_id": "x",
        "types": ["locality"],
    }


def test_geocode_non_ok_carries_reason():
    out = _coerce_geocode(
        {"status": "REQUEST_DENIED", "error_message": "API key bad"}
    )
    assert out["ok"] is False
    assert out["status"] == "REQUEST_DENIED"
    assert "API key bad" in out["reason"]


def test_geocode_zero_results():
    out = _coerce_geocode({"status": "OK", "results": []})
    assert out["ok"] is False
    assert out["status"] == "ZERO_RESULTS"


def test_directions_ok_payload():
    out = _coerce_directions(
        {
            "status": "OK",
            "routes": [
                {
                    "summary": "I-5 N",
                    "legs": [
                        {
                            "distance": {"value": 18000, "text": "18 km"},
                            "duration": {"value": 1200, "text": "20 mins"},
                            "start_address": "A",
                            "end_address": "B",
                        }
                    ],
                }
            ],
        }
    )
    assert out["ok"] is True
    assert out["distance_m"] == 18000
    assert out["duration_s"] == 1200
    assert out["summary"] == "I-5 N"


def test_places_ok_payload():
    out = _coerce_places(
        {
            "places": [
                {
                    "id": "1",
                    "displayName": {"text": "Stratus HQ"},
                    "formattedAddress": "Renton",
                    "location": {"latitude": 47.5, "longitude": -122.2},
                    "rating": 4.5,
                    "types": ["office"],
                }
            ]
        }
    )
    assert out["ok"] is True
    assert out["places"][0]["name"] == "Stratus HQ"


def test_places_error_payload():
    out = _coerce_places({"error": {"message": "bad request"}})
    assert out["ok"] is False
    assert "bad request" in out["reason"]


def test_coerce_latlng_from_string():
    got = _coerce_latlng("47.5, -122.2")
    assert got == {"latitude": 47.5, "longitude": -122.2}


def test_coerce_latlng_from_dict_handles_both_naming_conventions():
    assert _coerce_latlng({"lat": 1, "lng": 2}) == {"latitude": 1.0, "longitude": 2.0}
    assert _coerce_latlng({"latitude": 1, "longitude": 2}) == {
        "latitude": 1.0,
        "longitude": 2.0,
    }


def test_coerce_latlng_rejects_malformed():
    with pytest.raises(ToolDenied):
        _coerce_latlng("not a latlng")
    with pytest.raises(ToolDenied):
        _coerce_latlng({"lat": 1})  # missing lng


# ---- MapsClient end-to-end with a fake httpx client ----


class FakeResponse:
    def __init__(self, body: Any, status: int = 200) -> None:
        self._body = body
        self.status_code = status

    def json(self) -> Any:
        return self._body


class FakeHttp:
    """Records calls and returns canned responses."""

    def __init__(self, responses: list[FakeResponse]) -> None:
        self._responses = list(responses)
        self.calls: list[tuple[str, str, dict, dict | None, dict | None]] = []

    async def get(self, url, params=None):
        self.calls.append(("GET", url, params, None, None))
        return self._responses.pop(0)

    async def post(self, url, json=None, headers=None):
        self.calls.append(("POST", url, {}, json, headers))
        return self._responses.pop(0)

    async def aclose(self):
        pass


def test_constructor_requires_api_key():
    with pytest.raises(ValueError):
        MapsClient(api_key="")


async def test_geocode_round_trip():
    fake = FakeHttp(
        [
            FakeResponse(
                {
                    "status": "OK",
                    "results": [
                        {
                            "formatted_address": "Renton, WA",
                            "geometry": {"location": {"lat": 47.5, "lng": -122.2}},
                            "place_id": "x",
                            "types": ["locality"],
                        }
                    ],
                }
            )
        ]
    )
    client = MapsClient(api_key="K", http=fake)
    out = await client.geocode("Renton, WA")
    assert out["ok"] is True
    assert out["lat"] == 47.5
    # Confirm we passed the API key, not logged it.
    method, url, params, *_ = fake.calls[0]
    assert method == "GET"
    assert params["key"] == "K"


async def test_directions_round_trip():
    fake = FakeHttp(
        [
            FakeResponse(
                {
                    "status": "OK",
                    "routes": [
                        {
                            "summary": "I-5",
                            "legs": [
                                {
                                    "distance": {"value": 100, "text": "0.1 km"},
                                    "duration": {"value": 60, "text": "1 min"},
                                    "start_address": "A",
                                    "end_address": "B",
                                }
                            ],
                        }
                    ],
                }
            )
        ]
    )
    client = MapsClient(api_key="K", http=fake)
    out = await client.directions("A", "B")
    assert out["ok"] is True
    assert out["duration_s"] == 60


async def test_directions_rejects_bad_mode():
    fake = FakeHttp([])
    client = MapsClient(api_key="K", http=fake)
    with pytest.raises(ToolDenied, match="bad mode"):
        await client.directions("A", "B", mode="rocket")


async def test_directions_rejects_empty_origin():
    fake = FakeHttp([])
    client = MapsClient(api_key="K", http=fake)
    with pytest.raises(ToolDenied, match="empty"):
        await client.directions("", "B")


async def test_places_passes_locationbias_when_near_given():
    fake = FakeHttp([FakeResponse({"places": []})])
    client = MapsClient(api_key="K", http=fake)
    await client.places("ramen", near="47.5, -122.2", k=3)
    method, url, _, body, headers = fake.calls[0]
    assert method == "POST"
    assert body["textQuery"] == "ramen"
    assert body["maxResultCount"] == 3
    assert body["locationBias"]["circle"]["center"]["latitude"] == 47.5
    assert headers["X-Goog-Api-Key"] == "K"


async def test_places_clamps_k():
    fake = FakeHttp([FakeResponse({"places": []})])
    client = MapsClient(api_key="K", http=fake)
    await client.places("ramen", k=999)
    body = fake.calls[0][3]
    assert body["maxResultCount"] <= 10


async def test_geocode_rejects_empty():
    fake = FakeHttp([])
    client = MapsClient(api_key="K", http=fake)
    with pytest.raises(ToolDenied, match="empty"):
        await client.geocode("")


async def test_http_4xx_becomes_tool_denied():
    fake = FakeHttp([FakeResponse({"x": "y"}, status=403)])
    client = MapsClient(api_key="K", http=fake)
    with pytest.raises(ToolDenied, match="http 403"):
        await client.geocode("anywhere")
