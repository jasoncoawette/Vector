from __future__ import annotations

import re
import secrets
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from .errors import NeedsConfirm, ToolDenied

CONFIRM_TTL_S = 120

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@dataclass
class PendingAction:
    ts: float
    op: str
    fingerprint: str


@dataclass
class ConfirmGate:
    """Shared two-step confirm gate for outbound mutations."""

    _pending: dict[str, PendingAction] = field(default_factory=dict)

    def request(self, op: str, fingerprint: str) -> str:
        token = secrets.token_urlsafe(16)
        self._pending[token] = PendingAction(time.time(), op, fingerprint)
        return token

    def consume(self, token: str, op: str, fingerprint: str) -> None:
        entry = self._pending.pop(token, None)
        if entry is None:
            raise ToolDenied("invalid or expired confirm token")
        if time.time() - entry.ts > CONFIRM_TTL_S:
            raise ToolDenied("confirm token expired")
        if entry.op != op or entry.fingerprint != fingerprint:
            raise ToolDenied("confirm token does not match")


def _email_fingerprint(to: str, subject: str, body: str) -> str:
    return f"{to.lower()}|{subject}|{len(body)}"


@dataclass
class GmailClient:
    sender: Callable[[str, str, str], Awaitable[dict]]
    gate: ConfirmGate = field(default_factory=ConfirmGate)

    async def send(
        self, to: str, subject: str, body: str, confirm_token: str | None = None
    ) -> dict:
        if not EMAIL_RE.match(to):
            raise ToolDenied(f"bad recipient: {to}")
        if not subject.strip():
            raise ToolDenied("empty subject")
        fp = _email_fingerprint(to, subject, body)
        if confirm_token is None:
            token = self.gate.request("gmail.send", fp)
            raise NeedsConfirm(f"send to {to} needs confirm", token)
        self.gate.consume(confirm_token, "gmail.send", fp)
        return await self.sender(to, subject, body)


@dataclass
class CalendarClient:
    writer: Callable[[dict], Awaitable[dict]]
    gate: ConfirmGate = field(default_factory=ConfirmGate)

    async def create_event(
        self,
        title: str,
        start_iso: str,
        end_iso: str,
        confirm_token: str | None = None,
    ) -> dict:
        if not title.strip():
            raise ToolDenied("empty title")
        if start_iso >= end_iso:
            raise ToolDenied("start must precede end")
        fp = f"{title}|{start_iso}|{end_iso}"
        event = {"title": title, "start": start_iso, "end": end_iso}
        if confirm_token is None:
            token = self.gate.request("calendar.create", fp)
            raise NeedsConfirm(f"create event {title} needs confirm", token)
        self.gate.consume(confirm_token, "calendar.create", fp)
        return await self.writer(event)


@dataclass
class RemindersClient:
    writer: Callable[[dict], Awaitable[dict]]

    async def add(self, title: str, due_iso: str | None = None) -> dict:
        if not title.strip():
            raise ToolDenied("empty title")
        return await self.writer({"title": title, "due": due_iso})
