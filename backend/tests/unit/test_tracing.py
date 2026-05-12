from __future__ import annotations

from pathlib import Path

import pytest

from vector.tracing import current_trace_id, ensure_trace_id, new_trace_id, trace


def test_default_is_none():
    assert current_trace_id() is None


def test_trace_binds_and_unbinds():
    assert current_trace_id() is None
    with trace("abc123") as tid:
        assert tid == "abc123"
        assert current_trace_id() == "abc123"
    assert current_trace_id() is None


def test_trace_mints_when_none_given():
    with trace() as tid:
        assert tid
        assert current_trace_id() == tid


def test_nested_traces_restore_outer():
    with trace("outer"):
        with trace("inner"):
            assert current_trace_id() == "inner"
        assert current_trace_id() == "outer"


def test_ensure_trace_id_mints_if_missing():
    # Outside any trace() context. ensure_trace_id() sets the contextvar
    # but doesn't have a "with" boundary, so its lifetime is the test
    # function. Just verify it returns a value.
    tid = ensure_trace_id()
    assert tid


def test_new_trace_id_is_unique():
    seen = {new_trace_id() for _ in range(100)}
    assert len(seen) == 100


async def test_trace_id_survives_await_chain():
    """contextvars are propagated across await points."""
    import asyncio

    async def inner():
        await asyncio.sleep(0)
        return current_trace_id()

    with trace("survives") as tid:
        result = await inner()
        assert result == tid
