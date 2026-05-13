from __future__ import annotations

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


# --- Orchestration tools --------------------------------------------
# Surfaced only to the orchestrator profile. The builder gates registration
# on the presence of an AgentManager + PlanRunner so the master registry
# stays well-defined when those clients aren't wired (e.g. early startup).


class AgentSpawnToolArgs(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    prompt: str = Field(min_length=1, max_length=8000)
    files: list[str] = Field(default_factory=list, max_length=32)
    cost_cap_usd: float = Field(default=1.0, gt=0, le=10.0)
    timeout_s: int = Field(default=600, ge=1, le=3600)
    success_criteria: str | None = Field(default=None, max_length=2000)
    max_attempts: int = Field(default=3, ge=1, le=5)


class AgentFanOutToolArgs(BaseModel):
    specs: list[AgentSpawnToolArgs] = Field(min_length=1, max_length=8)


class PlansSubmitToolArgs(BaseModel):
    # The dict shape is validated through PlanIn/build_plan inside the
    # handler so this tool stays in lockstep with the /plans HTTP route.
    goal: str = Field(min_length=1, max_length=2000)
    steps: list[dict] = Field(min_length=1, max_length=16)
