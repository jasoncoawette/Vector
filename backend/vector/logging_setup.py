"""Structured JSON logging keyed by trace_id.

Every log record from Vector loggers ships as one JSON line with:
- ts (epoch float)
- level
- logger
- msg
- trace_id (from contextvar, when bound)
- any extras passed via `logger.<level>("...", extra={...})`

A debugging agent can grep these by trace_id and reconstruct the
chain alongside the audit_log and events tables.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any

from .tracing import current_trace_id

# Standard LogRecord attributes we never want re-emitted as extras.
_RESERVED = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "message",
        "module",
        "msecs",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "thread",
        "threadName",
        "taskName",
    }
)


class JsonFormatter(logging.Formatter):
    """Render a LogRecord as a single-line JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": record.created,
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        trace_id = current_trace_id()
        if trace_id is not None:
            payload["trace_id"] = trace_id
        for key, value in record.__dict__.items():
            if key in _RESERVED or key.startswith("_"):
                continue
            try:
                json.dumps(value, default=str)
                payload[key] = value
            except (TypeError, ValueError):
                payload[key] = str(value)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        try:
            return json.dumps(payload, default=str)
        except (TypeError, ValueError):
            return json.dumps({"ts": record.created, "level": record.levelname, "msg": str(record.msg)})


def configure(level: int | str | None = None) -> None:
    """Install the JSON formatter on the root logger.

    Idempotent — calling twice does not double-attach. Honors the
    VECTOR_LOG_LEVEL env var (default INFO). Set VECTOR_LOG_FORMAT=plain
    to opt out of JSON during local debugging.
    """
    if level is None:
        level = os.environ.get("VECTOR_LOG_LEVEL", "INFO")
    if isinstance(level, str):
        level = level.upper()
    fmt = os.environ.get("VECTOR_LOG_FORMAT", "json").lower()

    root = logging.getLogger()
    root.setLevel(level)
    # Strip any handlers we installed previously so configure() is idempotent.
    for h in list(root.handlers):
        if getattr(h, "_vector_handler", False):
            root.removeHandler(h)

    handler = logging.StreamHandler(stream=sys.stderr)
    handler._vector_handler = True  # type: ignore[attr-defined]
    if fmt == "plain":
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
        )
    else:
        handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
