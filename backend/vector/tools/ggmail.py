"""Gmail send — RFC 2822 message, base64url-encoded, POSTed to
gmail.users.messages.send.

Two ops:
  - gmail.draft(to, subject, body)  no confirm; lands in Drafts only
  - gmail.send(to, subject, body)   confirm-token gate; actually sends

Drafts are free of consequence — useful for "show me what you'd send";
the actual send is gated behind ConfirmGate so the brain can't
accidentally fire a message at someone Jason cares about.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass, field
from email.message import EmailMessage

from .errors import NeedsConfirm, ToolDenied
from .google_api import GoogleApiClient
from .outbound import EMAIL_RE, ConfirmGate

GMAIL_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"

MAX_BODY_BYTES = 50_000
MAX_SUBJECT_BYTES = 998  # RFC 2822 line length cap


def _build_message(to: str, subject: str, body: str) -> str:
    msg = EmailMessage()
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    raw = msg.as_bytes()
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _email_fingerprint(to: str, subject: str, body: str) -> str:
    return f"{to.lower()}|{subject}|{len(body)}|{hash(body) & 0xFFFFFFFF}"


@dataclass
class GmailClient:
    api: GoogleApiClient
    gate: ConfirmGate = field(default_factory=ConfirmGate)

    def _validate(self, to: str, subject: str, body: str) -> None:
        if not EMAIL_RE.match(to):
            raise ToolDenied(f"bad recipient: {to}")
        if not subject.strip():
            raise ToolDenied("empty subject")
        if len(subject.encode("utf-8")) > MAX_SUBJECT_BYTES:
            raise ToolDenied("subject too long")
        if len(body.encode("utf-8")) > MAX_BODY_BYTES:
            raise ToolDenied("body too long")

    async def draft(self, *, to: str, subject: str, body: str) -> dict:
        self._validate(to, subject, body)
        raw = _build_message(to, subject, body)
        payload = await self.api.request(
            "POST",
            f"{GMAIL_BASE}/drafts",
            json_body={"message": {"raw": raw}},
        )
        return {
            "id": payload.get("id"),
            "message_id": (payload.get("message") or {}).get("id"),
            "to": to,
            "subject": subject,
        }

    async def send(
        self,
        *,
        to: str,
        subject: str,
        body: str,
        confirm_token: str | None = None,
    ) -> dict:
        self._validate(to, subject, body)
        fingerprint = _email_fingerprint(to, subject, body)
        if confirm_token is None:
            token = self.gate.request("gmail.send", fingerprint)
            raise NeedsConfirm(f"send to {to} needs confirm", token)
        self.gate.consume(confirm_token, "gmail.send", fingerprint)

        raw = _build_message(to, subject, body)
        payload = await self.api.request(
            "POST",
            f"{GMAIL_BASE}/messages/send",
            json_body={"raw": raw},
        )
        return {
            "id": payload.get("id"),
            "thread_id": payload.get("threadId"),
            "to": to,
            "subject": subject,
        }
