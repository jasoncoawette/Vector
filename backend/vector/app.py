from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import audit
from .config import get_settings
from .tools.builder import build_default_registry
from .tools.errors import NeedsConfirm, ToolDenied, ToolError
from .tools.files import FileGuard
from .tools.registry import Registry

GREETING_USER = "Jason"

app = FastAPI(title="Vector", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


_registry: Registry | None = None


def get_registry() -> Registry:
    global _registry
    if _registry is None:
        s = get_settings()
        guard = FileGuard(read_root=s.workspace.parent, write_root=s.workspace)
        _registry = build_default_registry(guard)
    return _registry


def set_registry(reg: Registry | None) -> None:
    global _registry
    _registry = reg


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True, "build": get_settings().build_hash}


@app.get("/config")
def get_config() -> dict:
    return get_settings().redacted()


@app.post("/config")
def update_config(authorization: str | None = Header(default=None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "config writes not wired yet")


def _greeting_for(now: datetime) -> str:
    hour = now.hour
    if hour < 12:
        part = "Good morning"
    elif hour < 18:
        part = "Good afternoon"
    else:
        part = "Good evening"
    return f"{part} {GREETING_USER}."


@app.get("/voice/greeting")
def greeting() -> dict:
    return {"text": _greeting_for(datetime.now()), "user": GREETING_USER}


@app.get("/tools")
def list_tools(reg: Registry = Depends(get_registry)) -> dict:
    return {"tools": reg.list()}


class ToolCallBody(BaseModel):
    name: str = Field(min_length=1)
    args: dict[str, Any] = Field(default_factory=dict)
    caller: str = "user"


@app.post("/tools/call")
def call_tool(body: ToolCallBody, reg: Registry = Depends(get_registry)) -> dict:
    try:
        result = reg.call(body.name, body.args)
        audit.record(body.name, body.caller, body.args, result, ok=True)
        return {"ok": True, "result": result}
    except NeedsConfirm as e:
        audit.record(body.name, body.caller, body.args, {"reason": str(e)}, ok=False)
        return {"ok": False, "needs_confirm": True, "token": e.token, "reason": str(e)}
    except ToolDenied as e:
        audit.record(body.name, body.caller, body.args, {"reason": str(e)}, ok=False)
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(e)) from e
    except ToolError as e:
        audit.record(body.name, body.caller, body.args, {"reason": str(e)}, ok=False)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, str(e)) from e
