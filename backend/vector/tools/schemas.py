from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class FileReadArgs(BaseModel):
    path: str = Field(min_length=1)


class FileWriteArgs(BaseModel):
    path: str = Field(min_length=1)
    content: str
    confirm: bool = False


class FileDeleteArgs(BaseModel):
    path: str = Field(min_length=1)
    confirm_token: str | None = None


class MemorySearchArgs(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    kind: str | None = Field(default=None, max_length=64)
    k: int = Field(default=5, ge=1, le=20)


class MemoryAddArgs(BaseModel):
    kind: str = Field(min_length=1, max_length=64)
    text: str = Field(min_length=1, max_length=20_000)
    meta: dict | None = None


# --- Obsidian vault tool ---------------------------------------------


class ObsidianReadArgs(BaseModel):
    title: str = Field(min_length=1, max_length=512)


class ObsidianWriteArgs(BaseModel):
    title: str = Field(min_length=1, max_length=512)
    body: str = Field(max_length=1_000_000)


class ObsidianAppendArgs(BaseModel):
    title: str = Field(min_length=1, max_length=512)
    body: str = Field(min_length=1, max_length=1_000_000)


class ObsidianSearchArgs(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    k: int = Field(default=5, ge=1, le=20)


class ObsidianBacklinksArgs(BaseModel):
    title: str = Field(min_length=1, max_length=512)


class ObsidianListArgs(BaseModel):
    pass


# --- Google Maps tool -------------------------------------------------


class MapsGeocodeArgs(BaseModel):
    address: str = Field(min_length=1, max_length=500)


class MapsDirectionsArgs(BaseModel):
    origin: str = Field(min_length=1, max_length=500)
    destination: str = Field(min_length=1, max_length=500)
    mode: str = Field(default="driving", max_length=20)


class MapsPlacesArgs(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    near: str | None = Field(default=None, max_length=80)
    k: int = Field(default=5, ge=1, le=10)


# --- Google Calendar tool --------------------------------------------


class GCalListArgs(BaseModel):
    within_hours: int = Field(default=72, ge=1, le=336)
    max_results: int = Field(default=20, ge=1, le=50)


class GCalCreateArgs(BaseModel):
    summary: str = Field(min_length=1, max_length=400)
    start_iso: str = Field(min_length=1, max_length=64)
    end_iso: str = Field(min_length=1, max_length=64)
    location: str | None = Field(default=None, max_length=400)
    description: str | None = Field(default=None, max_length=8000)
    confirm_token: str | None = None


# --- Gmail tool -------------------------------------------------------


class GmailDraftArgs(BaseModel):
    to: str = Field(min_length=1, max_length=200)
    subject: str = Field(min_length=1, max_length=998)
    body: str = Field(max_length=50_000)


class GmailSendArgs(BaseModel):
    to: str = Field(min_length=1, max_length=200)
    subject: str = Field(min_length=1, max_length=998)
    body: str = Field(max_length=50_000)
    confirm_token: str | None = None


# --- Debug / telemetry tools (read-only, debugger profile) -----------


class EventsRecentArgs(BaseModel):
    limit: int = Field(default=50, ge=1, le=500)


class EventsByTraceArgs(BaseModel):
    trace_id: str = Field(min_length=1, max_length=64)


class AuditTailArgs(BaseModel):
    limit: int = Field(default=50, ge=1, le=500)


class AuditByTraceArgs(BaseModel):
    trace_id: str = Field(min_length=1, max_length=64)


class RunsRecentArgs(BaseModel):
    limit: int = Field(default=20, ge=1, le=200)
    status: str | None = Field(default=None, max_length=32)


class RunsGetArgs(BaseModel):
    run_id: str = Field(min_length=1, max_length=64)


class RoutingStatsArgs(BaseModel):
    pass  # no args


# --- Shell tools (self_healer only) ----------------------------------


class ShellRunTestsArgs(BaseModel):
    path: str | None = Field(default=None, max_length=500)
    framework: Literal["pytest", "vitest"] = "pytest"


class ShellRunLintArgs(BaseModel):
    path: str = Field(min_length=1, max_length=500)
    tool: Literal["ruff", "svelte-check"] = "ruff"
