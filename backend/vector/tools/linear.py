from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

import httpx

LinearFetcher = Callable[[], Awaitable[list[dict]]]


@dataclass
class CachedIssues:
    fetched_at: float
    issues: list[dict]


@dataclass
class LinearClient:
    api_key: str
    fetcher: LinearFetcher | None = None
    _cache: CachedIssues | None = field(default=None, init=False)
    _stale_after_s: int = 300

    def __post_init__(self) -> None:
        if not self.api_key and self.fetcher is None:
            raise ValueError("Linear API key required")

    async def _default_fetch(self) -> list[dict]:
        query = "{ issues(first: 50) { nodes { id title state { name } priority } } }"
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.post(
                "https://api.linear.app/graphql",
                json={"query": query},
                headers={"Authorization": self.api_key},
            )
            r.raise_for_status()
            data = r.json()
            return data["data"]["issues"]["nodes"]

    async def list_open(self) -> dict:
        fetch = self.fetcher or self._default_fetch
        try:
            issues = await fetch()
            self._cache = CachedIssues(fetched_at=time.time(), issues=issues)
            return {"issues": issues, "stale": False, "source": "remote"}
        except (httpx.HTTPError, asyncio.TimeoutError, OSError) as e:
            if self._cache is None:
                return {"issues": [], "stale": True, "source": "empty", "error": str(e)}
            return {
                "issues": self._cache.issues,
                "stale": True,
                "source": "cache",
                "cached_age_s": int(time.time() - self._cache.fetched_at),
            }

    def prime_cache(self, issues: list[dict]) -> None:
        self._cache = CachedIssues(fetched_at=time.time(), issues=issues)
