from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Any

logger = logging.getLogger("vector.audit")


def _hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, default=str).encode()
    return hashlib.sha256(payload).hexdigest()[:16]


def record(tool: str, caller: str, args: dict, result: Any, ok: bool) -> dict:
    entry = {
        "ts": time.time(),
        "tool": tool,
        "caller": caller,
        "args_hash": _hash(args),
        "result_hash": _hash(result),
        "ok": ok,
    }
    logger.info("audit %s", json.dumps(entry))
    return entry
