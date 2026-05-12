from __future__ import annotations

import io
import json
import logging

import pytest

from vector import logging_setup
from vector.tracing import trace


def _emit(formatter: logging_setup.JsonFormatter, **record_kwargs) -> dict:
    record = logging.LogRecord(
        name=record_kwargs.pop("name", "vector.test"),
        level=record_kwargs.pop("level", logging.INFO),
        pathname=__file__,
        lineno=1,
        msg=record_kwargs.pop("msg", "hello"),
        args=None,
        exc_info=None,
    )
    for k, v in record_kwargs.items():
        setattr(record, k, v)
    return json.loads(formatter.format(record))


def test_json_formatter_basic_shape():
    f = logging_setup.JsonFormatter()
    out = _emit(f)
    assert out["level"] == "INFO"
    assert out["logger"] == "vector.test"
    assert out["msg"] == "hello"
    assert "ts" in out
    # No trace bound in this context.
    assert "trace_id" not in out


def test_json_formatter_picks_up_trace_id():
    f = logging_setup.JsonFormatter()
    with trace("abc123"):
        out = _emit(f)
    assert out["trace_id"] == "abc123"


def test_json_formatter_includes_extras():
    f = logging_setup.JsonFormatter()
    out = _emit(f, cost_delta=0.002, run_id="r1", latency_ms=42.5)
    assert out["cost_delta"] == pytest.approx(0.002)
    assert out["run_id"] == "r1"
    assert out["latency_ms"] == pytest.approx(42.5)


def test_json_formatter_skips_reserved_attrs():
    f = logging_setup.JsonFormatter()
    out = _emit(f)
    # Standard LogRecord internals shouldn't leak into payload.
    assert "pathname" not in out
    assert "filename" not in out
    assert "process" not in out


def test_json_formatter_stringifies_non_json_safe_extras():
    f = logging_setup.JsonFormatter()

    class NotJsonable:
        def __repr__(self):
            return "NotJsonable()"

    out = _emit(f, weird=NotJsonable())
    assert out["weird"] == "NotJsonable()"


def test_configure_is_idempotent():
    logging_setup.configure()
    handlers_before = list(logging.getLogger().handlers)
    logging_setup.configure()
    handlers_after = list(logging.getLogger().handlers)
    # Exactly one vector-tagged handler in either case.
    vector_handlers_after = [h for h in handlers_after if getattr(h, "_vector_handler", False)]
    assert len(vector_handlers_after) == 1


def test_configure_honors_plain_format_env(monkeypatch):
    monkeypatch.setenv("VECTOR_LOG_FORMAT", "plain")
    logging_setup.configure()
    root = logging.getLogger()
    handler = next(h for h in root.handlers if getattr(h, "_vector_handler", False))
    assert not isinstance(handler.formatter, logging_setup.JsonFormatter)


def test_end_to_end_emits_json_line():
    """Configure, log, capture — verify one JSON line on stderr."""
    buf = io.StringIO()
    handler = logging.StreamHandler(stream=buf)
    handler.setFormatter(logging_setup.JsonFormatter())
    logger = logging.getLogger("vector.e2e.json")
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.INFO)
    with trace("e2e-trace"):
        logger.info("step done", extra={"step": "thinking", "cost_delta": 0.0012})
    line = buf.getvalue().strip()
    parsed = json.loads(line)
    assert parsed["trace_id"] == "e2e-trace"
    assert parsed["step"] == "thinking"
    assert parsed["cost_delta"] == pytest.approx(0.0012)
    assert parsed["msg"] == "step done"
