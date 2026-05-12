"""Trace IDs propagated through async call chains via contextvars.

Every turn / webhook / spawn gets a fresh trace_id at the entry point.
Downstream emitters (audit, routing, agent manager, events) read the
current id without needing it threaded through every signature.

A trace_id pins together the full chain: voice turn -> brain plan ->
tool call -> agent spawn -> verifier check -> retry. That single thread
is what the debugging agent pulls on to reconstruct an error path.
"""
from __future__ import annotations

import contextvars
import uuid
from contextlib import contextmanager
from typing import Iterator

_trace_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "vector_trace_id", default=None
)


def new_trace_id() -> str:
    return uuid.uuid4().hex[:16]


def current_trace_id() -> str | None:
    return _trace_id.get()


@contextmanager
def trace(trace_id: str | None = None) -> Iterator[str]:
    """Bind a trace_id for the duration of the `with` block."""
    tid = trace_id or new_trace_id()
    token = _trace_id.set(tid)
    try:
        yield tid
    finally:
        _trace_id.reset(token)


def ensure_trace_id() -> str:
    """Return the current trace_id, creating one if none is bound.

    Useful at emit points that may be called from contexts without an
    explicit `with trace()` (e.g. background tasks, legacy callers)."""
    tid = current_trace_id()
    if tid is None:
        tid = new_trace_id()
        _trace_id.set(tid)
    return tid
