from __future__ import annotations

from dataclasses import dataclass, field
from typing import Awaitable, Callable
from urllib.parse import urlparse

from .errors import NeedsConfirm, ToolDenied
from .outbound import ConfirmGate


@dataclass
class FetchedPage:
    url: str
    title: str
    text: str
    status: int = 200
    final_url: str | None = None


PageFetcher = Callable[[str], Awaitable[FetchedPage]]
FormSubmitter = Callable[[str, dict[str, str]], Awaitable[FetchedPage]]


LOGIN_HINTS = ("sign in", "log in", "log-in", "login", "password")
CAPTCHA_HINTS = ("captcha", "recaptcha", "are you a robot", "cf-challenge")
TWOFA_HINTS = ("verification code", "two-factor", "2fa", "authenticator", "enter code")


def _host_allowed(url: str, safe_hosts: tuple[str, ...]) -> bool:
    host = (urlparse(url).hostname or "").lower()
    if not host:
        return False
    return any(host == h or host.endswith("." + h) for h in safe_hosts)


def _flags_for(page: FetchedPage) -> list[str]:
    body = (page.title + "\n" + page.text).lower()
    flags: list[str] = []
    if any(h in body for h in LOGIN_HINTS):
        flags.append("login_wall")
    if any(h in body for h in CAPTCHA_HINTS):
        flags.append("captcha")
    if any(h in body for h in TWOFA_HINTS):
        flags.append("2fa")
    return flags


@dataclass
class BrowserClient:
    fetcher: PageFetcher
    safe_hosts: tuple[str, ...]
    submitter: FormSubmitter | None = None
    gate: ConfirmGate = field(default_factory=ConfirmGate)

    async def fetch(self, url: str) -> dict:
        if not _host_allowed(url, self.safe_hosts):
            raise ToolDenied(f"host not on safe list: {url}")
        page = await self.fetcher(url)
        flags = _flags_for(page)
        if flags:
            return {
                "url": page.url,
                "title": page.title,
                "status": page.status,
                "text": "",
                "flags": flags,
                "hand_off": True,
            }
        return {
            "url": page.url,
            "title": page.title,
            "status": page.status,
            "text": page.text[:50_000],
            "flags": flags,
            "hand_off": False,
        }

    async def submit_form(
        self,
        url: str,
        fields: dict[str, str],
        *,
        confirm_token: str | None = None,
    ) -> dict:
        if self.submitter is None:
            raise ToolDenied("form submission not enabled")
        if not _host_allowed(url, self.safe_hosts):
            raise ToolDenied(f"host not on safe list: {url}")
        if not fields:
            raise ToolDenied("empty form fields")
        fingerprint = f"{url}|{sorted(fields.items())}"
        if confirm_token is None:
            token = self.gate.request("browser.submit", fingerprint)
            raise NeedsConfirm(f"form submit to {url} needs confirm", token)
        self.gate.consume(confirm_token, "browser.submit", fingerprint)
        page = await self.submitter(url, fields)
        return {
            "url": page.url,
            "title": page.title,
            "status": page.status,
            "flags": _flags_for(page),
        }
