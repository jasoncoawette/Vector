from __future__ import annotations

import pytest
import httpx

from vector.tools.linear import LinearClient


async def test_returns_remote_on_success():
    async def fake():
        return [{"id": "1", "title": "ship CLI", "state": {"name": "In Progress"}}]

    client = LinearClient(api_key="k", fetcher=fake)
    out = await client.list_open()
    assert out["stale"] is False
    assert out["source"] == "remote"
    assert out["issues"][0]["id"] == "1"


async def test_cache_falls_through_on_error():
    calls = {"n": 0}

    async def flaky():
        calls["n"] += 1
        if calls["n"] == 1:
            return [{"id": "1"}]
        raise httpx.ConnectError("down", request=httpx.Request("POST", "http://x"))

    client = LinearClient(api_key="k", fetcher=flaky)
    first = await client.list_open()
    assert first["source"] == "remote"
    second = await client.list_open()
    assert second["stale"] is True
    assert second["source"] == "cache"
    assert second["issues"][0]["id"] == "1"


async def test_empty_when_no_cache_and_error():
    async def boom():
        raise httpx.ConnectError("down", request=httpx.Request("POST", "http://x"))

    client = LinearClient(api_key="k", fetcher=boom)
    out = await client.list_open()
    assert out["stale"] is True
    assert out["source"] == "empty"
    assert out["issues"] == []


def test_requires_key_or_fetcher():
    with pytest.raises(ValueError):
        LinearClient(api_key="")
