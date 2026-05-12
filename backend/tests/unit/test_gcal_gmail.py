"""GCalClient + GmailClient against a fake GoogleApiClient."""
from __future__ import annotations

from typing import Any

import pytest

from vector.tools.errors import NeedsConfirm, ToolDenied
from vector.tools.gcal import GCalClient
from vector.tools.ggmail import GmailClient


class _FakeApi:
    """Records request() calls and returns canned dicts."""

    def __init__(self, responses: list[Any]) -> None:
        self._responses = list(responses)
        self.calls: list[dict] = []

    async def request(self, method, url, *, params=None, json_body=None, retry_on_401=True):
        self.calls.append(
            {"method": method, "url": url, "params": params, "json": json_body}
        )
        return self._responses.pop(0)


# ---- GCal ----


async def test_list_upcoming_returns_events():
    api = _FakeApi(
        [
            {
                "items": [
                    {
                        "id": "ev1",
                        "summary": "Stratus block",
                        "start": {"dateTime": "2026-05-12T05:00:00-07:00"},
                        "end": {"dateTime": "2026-05-12T07:15:00-07:00"},
                        "attendees": [{"email": "a@b.co"}],
                    }
                ]
            }
        ]
    )
    gcal = GCalClient(api=api)
    out = await gcal.list_upcoming(within_hours=24)
    assert len(out["events"]) == 1
    e = out["events"][0]
    assert e["summary"] == "Stratus block"
    assert e["attendees"] == ["a@b.co"]


async def test_list_upcoming_rejects_bad_window():
    api = _FakeApi([])
    gcal = GCalClient(api=api)
    with pytest.raises(ToolDenied):
        await gcal.list_upcoming(within_hours=0)
    with pytest.raises(ToolDenied):
        await gcal.list_upcoming(within_hours=10000)


async def test_create_event_requires_confirm():
    api = _FakeApi([])
    gcal = GCalClient(api=api)
    with pytest.raises(NeedsConfirm) as exc:
        await gcal.create_event(
            summary="Block",
            start_iso="2026-05-12T05:00:00-07:00",
            end_iso="2026-05-12T07:15:00-07:00",
        )
    # No POST happened yet.
    assert api.calls == []

    # Second call WITH the token actually writes.
    api._responses = [
        {
            "id": "new-id",
            "summary": "Block",
            "start": {"dateTime": "2026-05-12T05:00:00-07:00"},
            "end": {"dateTime": "2026-05-12T07:15:00-07:00"},
            "htmlLink": "https://...",
        }
    ]
    out = await gcal.create_event(
        summary="Block",
        start_iso="2026-05-12T05:00:00-07:00",
        end_iso="2026-05-12T07:15:00-07:00",
        confirm_token=exc.value.token,
    )
    assert out["id"] == "new-id"
    # POST body contains the summary + start + end.
    assert api.calls[0]["method"] == "POST"
    assert api.calls[0]["json"]["summary"] == "Block"


async def test_create_event_rejects_bad_range():
    api = _FakeApi([])
    gcal = GCalClient(api=api)
    with pytest.raises(ToolDenied, match="precede"):
        await gcal.create_event(
            summary="x",
            start_iso="2026-05-12T10:00:00-07:00",
            end_iso="2026-05-12T09:00:00-07:00",
        )


async def test_create_event_token_bound_to_fingerprint():
    api = _FakeApi([])
    gcal = GCalClient(api=api)
    with pytest.raises(NeedsConfirm) as exc:
        await gcal.create_event(
            summary="A",
            start_iso="2026-05-12T05:00:00-07:00",
            end_iso="2026-05-12T06:00:00-07:00",
        )
    # Use the token to try a DIFFERENT event — must fail.
    with pytest.raises(ToolDenied):
        await gcal.create_event(
            summary="TAMPERED",
            start_iso="2026-05-12T05:00:00-07:00",
            end_iso="2026-05-12T06:00:00-07:00",
            confirm_token=exc.value.token,
        )


# ---- Gmail ----


async def test_gmail_draft_no_confirm():
    api = _FakeApi(
        [{"id": "d1", "message": {"id": "m1"}}]
    )
    g = GmailClient(api=api)
    out = await g.draft(to="a@b.co", subject="hi", body="hello")
    assert out["id"] == "d1"
    # Body landed encoded as base64url under message.raw.
    body = api.calls[0]["json"]["message"]
    assert "raw" in body
    assert isinstance(body["raw"], str)


async def test_gmail_send_requires_confirm():
    api = _FakeApi([])
    g = GmailClient(api=api)
    with pytest.raises(NeedsConfirm) as exc:
        await g.send(to="a@b.co", subject="hi", body="hello")
    assert api.calls == []

    api._responses = [{"id": "msg-1", "threadId": "t-1"}]
    out = await g.send(
        to="a@b.co", subject="hi", body="hello", confirm_token=exc.value.token
    )
    assert out["id"] == "msg-1"
    assert api.calls[0]["method"] == "POST"
    assert api.calls[0]["url"].endswith("/messages/send")


async def test_gmail_send_rejects_bad_recipient():
    api = _FakeApi([])
    g = GmailClient(api=api)
    with pytest.raises(ToolDenied, match="bad recipient"):
        await g.send(to="not-an-email", subject="hi", body="body")


async def test_gmail_send_rejects_empty_subject():
    api = _FakeApi([])
    g = GmailClient(api=api)
    with pytest.raises(ToolDenied, match="empty subject"):
        await g.send(to="a@b.co", subject="   ", body="body")


async def test_gmail_send_rejects_oversize_body():
    api = _FakeApi([])
    g = GmailClient(api=api)
    huge = "x" * 60_000
    with pytest.raises(ToolDenied, match="body too long"):
        await g.send(to="a@b.co", subject="ok", body=huge)


async def test_gmail_send_token_bound_to_body():
    api = _FakeApi([])
    g = GmailClient(api=api)
    with pytest.raises(NeedsConfirm) as exc:
        await g.send(to="a@b.co", subject="hi", body="original")
    with pytest.raises(ToolDenied):
        await g.send(
            to="a@b.co",
            subject="hi",
            body="TAMPERED",
            confirm_token=exc.value.token,
        )
