from __future__ import annotations

from pathlib import Path

import pytest

from vector.memory import HashEmbedder, SqliteMemoryStore
from vector.store import connect
from vector.tools.builder import build_registry_for
from vector.tools.errors import ToolDenied
from vector.tools.files import FileGuard
from vector.tools.maps import MapsClient


class _FakeHttp:
    """Returns OK geocode for every GET; empty places for every POST."""

    async def get(self, url, params=None):
        class R:
            status_code = 200

            def json(self):
                return {
                    "status": "OK",
                    "results": [
                        {
                            "formatted_address": "fake",
                            "geometry": {"location": {"lat": 0, "lng": 0}},
                            "place_id": "x",
                            "types": [],
                        }
                    ],
                }

        return R()

    async def post(self, url, json=None, headers=None):
        class R:
            status_code = 200

            def json(self):
                return {"places": []}

        return R()

    async def aclose(self):
        pass


@pytest.fixture()
def setup(tmp_path: Path):
    conn = connect(tmp_path / "v.db", check_integrity=False)
    memory = SqliteMemoryStore(conn, HashEmbedder())
    read_root = tmp_path / "home"
    read_root.mkdir()
    guard = FileGuard(read_root=read_root, write_root=read_root / "ws")
    maps = MapsClient(api_key="K", http=_FakeHttp())  # type: ignore[arg-type]
    yield {"conn": conn, "memory": memory, "guard": guard, "maps": maps}
    conn.close()


def test_research_agent_gets_maps(setup):
    reg = build_registry_for("research", guard=setup["guard"], maps=setup["maps"])
    names = {t["name"] for t in reg.list()}
    assert {"maps.geocode", "maps.directions", "maps.places"} <= names


def test_writer_agent_gets_maps(setup):
    reg = build_registry_for("writer", guard=setup["guard"], maps=setup["maps"])
    names = {t["name"] for t in reg.list()}
    assert "maps.geocode" in names


def test_code_agent_blocked_from_maps(setup):
    reg = build_registry_for("code", guard=setup["guard"], maps=setup["maps"])
    names = {t["name"] for t in reg.list()}
    assert "maps.geocode" not in names


def test_security_agent_blocked_from_maps(setup):
    reg = build_registry_for("security", guard=setup["guard"], maps=setup["maps"])
    names = {t["name"] for t in reg.list()}
    assert "maps.geocode" not in names


def test_no_api_key_means_no_maps_tools(setup):
    reg = build_registry_for("research", guard=setup["guard"], maps=None)
    names = {t["name"] for t in reg.list()}
    assert "maps.geocode" not in names


async def test_acall_awaits_async_handler(setup):
    reg = build_registry_for("research", guard=setup["guard"], maps=setup["maps"])
    result = await reg.acall("maps.geocode", {"address": "Renton"})
    assert result["ok"] is True


async def test_acall_passes_sync_handler_through(setup):
    """Sync tools (like file.read) work through acall as well."""
    target = setup["guard"].write_root / "x.txt"
    target.write_text("hello")
    reg = build_registry_for("research", guard=setup["guard"], maps=setup["maps"])
    result = await reg.acall("file.read", {"path": str(target)})
    assert result["text"] == "hello"


async def test_acall_rejects_bad_args(setup):
    reg = build_registry_for("research", guard=setup["guard"], maps=setup["maps"])
    with pytest.raises(ToolDenied):
        await reg.acall("maps.geocode", {"address": ""})


def test_sync_call_returns_coroutine_for_async_tool(setup):
    """`call()` doesn't await — kept for backwards compat with sync
    callers but they need to know it returns a coroutine for async tools."""
    import asyncio

    reg = build_registry_for("research", guard=setup["guard"], maps=setup["maps"])
    result = reg.call("maps.geocode", {"address": "Renton"})
    assert asyncio.iscoroutine(result)
    # Clean up so we don't leak a never-awaited warning.
    result.close()
