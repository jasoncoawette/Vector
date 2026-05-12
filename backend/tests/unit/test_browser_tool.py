from __future__ import annotations

import pytest

from vector.tools.browser import BrowserClient, FetchedPage
from vector.tools.errors import NeedsConfirm, ToolDenied

SAFE = ("github.com", "linear.app", "sam.gov")


async def _fake_ok(url: str) -> FetchedPage:
    return FetchedPage(url=url, title="Hello", text="welcome to the page")


async def _fake_login(url: str) -> FetchedPage:
    return FetchedPage(url=url, title="Sign in", text="Enter your password")


async def _fake_captcha(url: str) -> FetchedPage:
    return FetchedPage(url=url, title="Verify", text="Please complete the reCAPTCHA")


async def _fake_2fa(url: str) -> FetchedPage:
    return FetchedPage(
        url=url, title="Authenticator", text="Enter the 6-digit verification code"
    )


async def test_fetch_safe_host_returns_text():
    c = BrowserClient(fetcher=_fake_ok, safe_hosts=SAFE)
    out = await c.fetch("https://github.com/org/repo")
    assert out["hand_off"] is False
    assert "welcome" in out["text"]


async def test_fetch_unsafe_host_denied():
    c = BrowserClient(fetcher=_fake_ok, safe_hosts=SAFE)
    with pytest.raises(ToolDenied, match="safe list"):
        await c.fetch("https://evil.example.com/x")


async def test_subdomain_match_allowed():
    c = BrowserClient(fetcher=_fake_ok, safe_hosts=SAFE)
    out = await c.fetch("https://api.github.com/repos")
    assert out["status"] == 200


async def test_lookalike_host_denied():
    c = BrowserClient(fetcher=_fake_ok, safe_hosts=SAFE)
    with pytest.raises(ToolDenied):
        await c.fetch("https://github.com.evil.com/x")


async def test_login_wall_hands_off():
    c = BrowserClient(fetcher=_fake_login, safe_hosts=SAFE)
    out = await c.fetch("https://github.com/private")
    assert out["hand_off"] is True
    assert "login_wall" in out["flags"]
    assert out["text"] == ""


async def test_captcha_hands_off():
    c = BrowserClient(fetcher=_fake_captcha, safe_hosts=SAFE)
    out = await c.fetch("https://sam.gov/x")
    assert "captcha" in out["flags"]


async def test_twofa_hands_off():
    c = BrowserClient(fetcher=_fake_2fa, safe_hosts=SAFE)
    out = await c.fetch("https://github.com/security")
    assert "2fa" in out["flags"]


async def test_form_submit_requires_confirm():
    submitted: list = []

    async def submit(url, fields):
        submitted.append((url, fields))
        return FetchedPage(url=url, title="ok", text="ok")

    c = BrowserClient(fetcher=_fake_ok, submitter=submit, safe_hosts=SAFE)
    with pytest.raises(NeedsConfirm) as exc:
        await c.submit_form("https://linear.app/x", {"q": "hi"})
    assert submitted == []
    out = await c.submit_form(
        "https://linear.app/x", {"q": "hi"}, confirm_token=exc.value.token
    )
    assert out["status"] == 200
    assert submitted == [("https://linear.app/x", {"q": "hi"})]


async def test_form_token_bound_to_fields():
    async def submit(url, fields):
        return FetchedPage(url=url, title="ok", text="ok")

    c = BrowserClient(fetcher=_fake_ok, submitter=submit, safe_hosts=SAFE)
    with pytest.raises(NeedsConfirm) as exc:
        await c.submit_form("https://linear.app/x", {"q": "hi"})
    with pytest.raises(ToolDenied):
        await c.submit_form(
            "https://linear.app/x", {"q": "TAMPERED"}, confirm_token=exc.value.token
        )


async def test_form_off_safelist_denied():
    async def submit(url, fields):
        return FetchedPage(url=url, title="ok", text="ok")

    c = BrowserClient(fetcher=_fake_ok, submitter=submit, safe_hosts=SAFE)
    with pytest.raises(ToolDenied):
        await c.submit_form("https://evil.com/x", {"q": "hi"})


async def test_text_truncated():
    async def big(url):
        return FetchedPage(url=url, title="big", text="x" * 200_000)

    c = BrowserClient(fetcher=big, safe_hosts=SAFE)
    out = await c.fetch("https://github.com/repo")
    assert len(out["text"]) <= 50_000
