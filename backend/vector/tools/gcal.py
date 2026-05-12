"""Google Calendar — list upcoming events + create new events.

Two operations:
  - gcal.list_upcoming(within_hours=72)   list events in a window
  - gcal.create_event(...)                with confirm-token gate

create_event reuses Phase 2's ConfirmGate so the brain has to go
through the two-step grant pattern before anything lands on Jason's
calendar.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from .errors import NeedsConfirm, ToolDenied
from .google_api import GoogleApiClient
from .outbound import ConfirmGate

CALENDAR_BASE = "https://www.googleapis.com/calendar/v3"

DEFAULT_CALENDAR_ID = "primary"
MAX_UPCOMING = 50


@dataclass
class GCalClient:
    api: GoogleApiClient
    gate: ConfirmGate = field(default_factory=ConfirmGate)

    async def list_upcoming(
        self,
        *,
        within_hours: int = 72,
        calendar_id: str = DEFAULT_CALENDAR_ID,
        max_results: int = 20,
    ) -> dict:
        if within_hours < 1 or within_hours > 24 * 14:
            raise ToolDenied("within_hours must be 1..336")
        max_results = max(1, min(max_results, MAX_UPCOMING))
        now = datetime.now(timezone.utc)
        future = now + timedelta(hours=within_hours)
        params = {
            "timeMin": now.isoformat().replace("+00:00", "Z"),
            "timeMax": future.isoformat().replace("+00:00", "Z"),
            "singleEvents": "true",
            "orderBy": "startTime",
            "maxResults": str(max_results),
        }
        payload = await self.api.request(
            "GET", f"{CALENDAR_BASE}/calendars/{calendar_id}/events", params=params
        )
        events = []
        for e in payload.get("items", []):
            events.append(
                {
                    "id": e.get("id"),
                    "summary": e.get("summary"),
                    "location": e.get("location"),
                    "start": (e.get("start") or {}).get("dateTime")
                    or (e.get("start") or {}).get("date"),
                    "end": (e.get("end") or {}).get("dateTime")
                    or (e.get("end") or {}).get("date"),
                    "hangoutLink": e.get("hangoutLink"),
                    "htmlLink": e.get("htmlLink"),
                    "attendees": [
                        a.get("email")
                        for a in (e.get("attendees") or [])
                        if a.get("email")
                    ],
                }
            )
        return {"events": events}

    async def create_event(
        self,
        *,
        summary: str,
        start_iso: str,
        end_iso: str,
        location: str | None = None,
        description: str | None = None,
        confirm_token: str | None = None,
        calendar_id: str = DEFAULT_CALENDAR_ID,
    ) -> dict:
        if not summary.strip():
            raise ToolDenied("empty summary")
        if not start_iso or not end_iso:
            raise ToolDenied("missing start or end")
        if start_iso >= end_iso:
            raise ToolDenied("start must precede end")
        fingerprint = f"{calendar_id}|{summary}|{start_iso}|{end_iso}|{location or ''}"
        if confirm_token is None:
            token = self.gate.request("gcal.create_event", fingerprint)
            raise NeedsConfirm(
                f"create '{summary}' at {start_iso} needs confirm", token
            )
        self.gate.consume(confirm_token, "gcal.create_event", fingerprint)

        body: dict = {
            "summary": summary,
            "start": {"dateTime": start_iso},
            "end": {"dateTime": end_iso},
        }
        if location:
            body["location"] = location
        if description:
            body["description"] = description
        payload = await self.api.request(
            "POST",
            f"{CALENDAR_BASE}/calendars/{calendar_id}/events",
            json_body=body,
        )
        return {
            "id": payload.get("id"),
            "htmlLink": payload.get("htmlLink"),
            "summary": payload.get("summary"),
            "start": (payload.get("start") or {}).get("dateTime"),
            "end": (payload.get("end") or {}).get("dateTime"),
        }
