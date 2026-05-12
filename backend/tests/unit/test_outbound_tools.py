from __future__ import annotations

import pytest

from vector.tools.errors import NeedsConfirm, ToolDenied
from vector.tools.outbound import CalendarClient, GmailClient, RemindersClient


async def test_gmail_send_requires_confirm():
    calls = []

    async def sender(to, subject, body):
        calls.append((to, subject, body))
        return {"id": "msg-1"}

    g = GmailClient(sender=sender)
    with pytest.raises(NeedsConfirm) as exc:
        await g.send("a@b.co", "Hi", "hello")
    assert calls == []

    result = await g.send("a@b.co", "Hi", "hello", confirm_token=exc.value.token)
    assert result["id"] == "msg-1"
    assert calls == [("a@b.co", "Hi", "hello")]


async def test_gmail_bad_recipient_denied():
    async def sender(to, subject, body):
        return {}

    g = GmailClient(sender=sender)
    with pytest.raises(ToolDenied, match="bad recipient"):
        await g.send("not-an-email", "Hi", "x")


async def test_gmail_token_does_not_match_different_body():
    async def sender(*a):
        return {"id": "1"}

    g = GmailClient(sender=sender)
    with pytest.raises(NeedsConfirm) as exc:
        await g.send("a@b.co", "Hi", "first body")
    with pytest.raises(ToolDenied, match="does not match"):
        await g.send("a@b.co", "Hi", "TAMPERED", confirm_token=exc.value.token)


async def test_calendar_event_requires_confirm():
    written = []

    async def writer(event):
        written.append(event)
        return {"id": "evt-1", **event}

    c = CalendarClient(writer=writer)
    with pytest.raises(NeedsConfirm) as exc:
        await c.create_event("Block", "2026-05-12T05:00", "2026-05-12T07:15")
    assert written == []
    out = await c.create_event(
        "Block",
        "2026-05-12T05:00",
        "2026-05-12T07:15",
        confirm_token=exc.value.token,
    )
    assert out["id"] == "evt-1"


async def test_calendar_rejects_bad_range():
    async def writer(e):
        return e

    c = CalendarClient(writer=writer)
    with pytest.raises(ToolDenied):
        await c.create_event("X", "2026-05-12T10:00", "2026-05-12T09:00")


async def test_reminders_writes_directly():
    written = []

    async def writer(r):
        written.append(r)
        return {"id": "r1", **r}

    r = RemindersClient(writer=writer)
    out = await r.add("Call Boeing", due_iso="2026-05-12T12:30")
    assert out["id"] == "r1"
    assert written[0]["title"] == "Call Boeing"


async def test_reminders_rejects_empty_title():
    async def writer(r):
        return r

    r = RemindersClient(writer=writer)
    with pytest.raises(ToolDenied):
        await r.add("  ")
