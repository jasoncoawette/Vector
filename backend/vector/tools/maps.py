"""Google Maps tool.

Three operations, all auth'd by an API key (no OAuth):
  - maps.geocode(address)            address -> lat/lng + components
  - maps.directions(origin, dest)    origin/dest -> route + drive time
  - maps.places(query, near=...)     text search -> list of places

The HTTP client is injectable so tests don't hit the real API. We use
the Google Maps Platform endpoints (the modern Places API takes
POST/JSON; Geocoding + Directions are GET with query params).

API key restriction: at the GCP console, restrict the key to your
Mac mini's IP and to the three APIs above. We never log or echo the
key, and config.SECRET_FIELDS redacts it on /config.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx

from .errors import ToolDenied

GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
DIRECTIONS_URL = "https://maps.googleapis.com/maps/api/directions/json"
PLACES_URL = "https://places.googleapis.com/v1/places:searchText"

MAX_RESULTS = 10
DEFAULT_TIMEOUT_S = 10.0


@dataclass
class MapsClient:
    api_key: str
    http: httpx.AsyncClient | None = None
    _owned_client: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        if not self.api_key:
            raise ValueError("Google Maps API key required")

    async def _client(self) -> httpx.AsyncClient:
        if self.http is None:
            self.http = httpx.AsyncClient(timeout=DEFAULT_TIMEOUT_S)
            self._owned_client = True
        return self.http

    async def aclose(self) -> None:
        if self._owned_client and self.http is not None:
            await self.http.aclose()

    # --- geocoding --------------------------------------------------

    async def geocode(self, address: str) -> dict:
        if not address.strip():
            raise ToolDenied("empty address")
        params = {"address": address.strip(), "key": self.api_key}
        client = await self._client()
        try:
            r = await client.get(GEOCODE_URL, params=params)
        except httpx.HTTPError as e:
            raise ToolDenied(f"geocode network error: {e}") from e
        return _coerce_geocode(_load_json(r))

    # --- directions -------------------------------------------------

    async def directions(
        self, origin: str, destination: str, *, mode: str = "driving"
    ) -> dict:
        if not origin.strip() or not destination.strip():
            raise ToolDenied("empty origin or destination")
        if mode not in ("driving", "walking", "bicycling", "transit"):
            raise ToolDenied(f"bad mode: {mode}")
        params = {
            "origin": origin.strip(),
            "destination": destination.strip(),
            "mode": mode,
            "key": self.api_key,
        }
        client = await self._client()
        try:
            r = await client.get(DIRECTIONS_URL, params=params)
        except httpx.HTTPError as e:
            raise ToolDenied(f"directions network error: {e}") from e
        return _coerce_directions(_load_json(r))

    # --- places text search -----------------------------------------

    async def places(self, query: str, *, near: str | None = None, k: int = 5) -> dict:
        if not query.strip():
            raise ToolDenied("empty query")
        k = max(1, min(k, MAX_RESULTS))
        body: dict[str, Any] = {"textQuery": query.strip(), "maxResultCount": k}
        if near:
            body["locationBias"] = {"circle": {"center": _coerce_latlng(near)}}
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self.api_key,
            "X-Goog-FieldMask": (
                "places.displayName,places.formattedAddress,places.location,"
                "places.rating,places.id,places.types"
            ),
        }
        client = await self._client()
        try:
            r = await client.post(PLACES_URL, json=body, headers=headers)
        except httpx.HTTPError as e:
            raise ToolDenied(f"places network error: {e}") from e
        return _coerce_places(_load_json(r))


# --- helpers -----------------------------------------------------------


def _load_json(r: httpx.Response) -> dict:
    if r.status_code >= 400:
        raise ToolDenied(f"google maps http {r.status_code}")
    try:
        return r.json()
    except ValueError as e:
        raise ToolDenied(f"bad json from google maps: {e}") from e


def _coerce_geocode(payload: dict) -> dict:
    status = payload.get("status")
    if status != "OK":
        return {"ok": False, "status": status, "reason": payload.get("error_message", "")}
    results = payload.get("results") or []
    if not results:
        return {"ok": False, "status": "ZERO_RESULTS"}
    first = results[0]
    loc = (first.get("geometry") or {}).get("location") or {}
    return {
        "ok": True,
        "address": first.get("formatted_address"),
        "lat": loc.get("lat"),
        "lng": loc.get("lng"),
        "place_id": first.get("place_id"),
        "types": first.get("types") or [],
    }


def _coerce_directions(payload: dict) -> dict:
    status = payload.get("status")
    if status != "OK":
        return {"ok": False, "status": status, "reason": payload.get("error_message", "")}
    routes = payload.get("routes") or []
    if not routes:
        return {"ok": False, "status": "ZERO_RESULTS"}
    legs = routes[0].get("legs") or []
    if not legs:
        return {"ok": False, "status": "NO_LEGS"}
    leg = legs[0]
    distance = leg.get("distance") or {}
    duration = leg.get("duration") or {}
    return {
        "ok": True,
        "distance_m": distance.get("value"),
        "distance_text": distance.get("text"),
        "duration_s": duration.get("value"),
        "duration_text": duration.get("text"),
        "start_address": leg.get("start_address"),
        "end_address": leg.get("end_address"),
        "summary": routes[0].get("summary"),
    }


def _coerce_places(payload: dict) -> dict:
    if "error" in payload:
        return {"ok": False, "reason": payload["error"].get("message", "unknown")}
    places = payload.get("places") or []
    return {
        "ok": True,
        "places": [
            {
                "id": p.get("id"),
                "name": (p.get("displayName") or {}).get("text"),
                "address": p.get("formattedAddress"),
                "lat": (p.get("location") or {}).get("latitude"),
                "lng": (p.get("location") or {}).get("longitude"),
                "rating": p.get("rating"),
                "types": p.get("types") or [],
            }
            for p in places
        ],
    }


def _coerce_latlng(value: str | dict) -> dict:
    """Accept either 'lat,lng' string or {'lat':..,'lng':..} dict.

    Google's locationBias.center wants {latitude, longitude}."""
    if isinstance(value, dict):
        lat = value.get("lat") or value.get("latitude")
        lng = value.get("lng") or value.get("longitude")
    elif isinstance(value, str) and "," in value:
        parts = [p.strip() for p in value.split(",", 1)]
        try:
            lat, lng = float(parts[0]), float(parts[1])
        except ValueError as e:
            raise ToolDenied(f"bad lat,lng: {value}") from e
    else:
        raise ToolDenied(f"bad lat,lng: {value}")
    if lat is None or lng is None:
        raise ToolDenied("missing lat or lng")
    return {"latitude": float(lat), "longitude": float(lng)}
