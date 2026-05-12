from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import audit
from .agents.types import AgentSpec, AgentType, RunStatus
from .auth import require_bearer
from .config import get_settings
from .deps import get_agents, get_db
from .engine import brief as brief_mod
from .engine import mission as mission_eng
from .engine import picker, review
from .engine import weekly as weekly_eng
from .store import metrics as metrics_store
from .store import tasks as tasks_repo
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


@app.on_event("startup")
def _on_start() -> None:
    audit.set_sink(get_db())


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


@app.get("/daily/picks")
def daily_picks(day: str | None = None) -> dict:
    target = day or datetime.now().date().isoformat()
    conn = get_db()
    picks = picker.pick_top(conn, day=target)
    picker.log_picks(conn, target, picks)
    return {
        "day": target,
        "picks": [
            {
                "task_id": p.task.id,
                "title": p.task.title,
                "score": p.score,
                "reason": p.reason,
            }
            for p in picks
        ],
    }


@app.get("/daily/brief")
def daily_brief() -> dict:
    now = datetime.now()
    conn = get_db()
    picks = picker.pick_top(conn, day=now.date().isoformat())
    text = brief_mod.render_morning_brief(picks, now=now, user=GREETING_USER)
    return {"text": text, "picks": len(picks)}


class OverrideBody(BaseModel):
    day: str = Field(min_length=1)
    removed_task_id: int
    added_task_id: int


@app.post("/daily/override", dependencies=[Depends(require_bearer)])
def daily_override(body: OverrideBody) -> dict:
    conn = get_db()
    weights = picker.record_override(
        conn,
        day=body.day,
        removed_task_id=body.removed_task_id,
        added_task_id=body.added_task_id,
    )
    return {"ok": True, "weights": weights}


class ReviewBody(BaseModel):
    day: str = Field(min_length=1)
    shipped_ids: list[int] = Field(default_factory=list)
    note: str | None = None


@app.post("/daily/review")
def daily_review(body: ReviewBody) -> dict:
    conn = get_db()
    r = review.record_review(
        conn, day=body.day, shipped_ids=body.shipped_ids, note=body.note
    )
    return {
        "day": r.day,
        "shipped_ids": r.shipped_ids,
        "slipped_ids": r.slipped_ids,
        "spoken": review.render_review(r, conn),
    }


class MetricBody(BaseModel):
    section: str = Field(min_length=1)
    name: str = Field(min_length=1)
    value: float
    unit: str | None = None


@app.post("/metrics")
def post_metric(body: MetricBody) -> dict:
    conn = get_db()
    try:
        mid = metrics_store.record(
            conn,
            section=body.section,
            name=body.name,
            value=body.value,
            unit=body.unit,
        )
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
    return {"id": mid}


@app.get("/metrics")
def get_metrics(section: str | None = None) -> dict:
    conn = get_db()
    try:
        points = metrics_store.latest(conn, section)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
    sections: dict[str, list[dict]] = {}
    for p in points:
        sections.setdefault(p.section, []).append(
            {
                "name": p.name,
                "value": p.value,
                "unit": p.unit,
                "recorded_at": p.recorded_at,
                "stale": metrics_store.is_stale(p),
            }
        )
    return {"sections": sections}


class TaskBody(BaseModel):
    external_id: str | None = None
    title: str = Field(min_length=1)
    source: str = "linear"
    tag: str = "process"
    priority: int = 3
    mission: str = "stratus"


@app.post("/tasks")
def upsert_task(body: TaskBody) -> dict:
    conn = get_db()
    tid = tasks_repo.upsert(
        conn,
        external_id=body.external_id,
        title=body.title,
        source=body.source,
        tag=body.tag,
        priority=body.priority,
        mission=body.mission,
    )
    return {"id": tid}


class AgentSpawnBody(BaseModel):
    type: AgentType
    prompt: str = Field(min_length=1, max_length=8000)
    files: list[str] = Field(default_factory=list)
    fallback_prompt: str | None = Field(default=None, max_length=8000)
    cost_cap_usd: float = Field(default=1.0, gt=0, le=10.0)
    timeout_s: int = Field(default=600, ge=1, le=3600)


@app.post("/agents/spawn", dependencies=[Depends(require_bearer)])
async def spawn_agent(body: AgentSpawnBody) -> dict:
    mgr = get_agents()
    spec = AgentSpec(
        type=body.type,
        prompt=body.prompt,
        files=frozenset(body.files),
        fallback_prompt=body.fallback_prompt,
        cost_cap_usd=body.cost_cap_usd,
        timeout_s=body.timeout_s,
    )
    run = await mgr.spawn(spec)
    audit.record("agents.spawn", "user", body.model_dump(), {"id": run.id}, ok=True)
    return run.summary()


@app.get("/agents")
def list_agents() -> dict:
    mgr = get_agents()
    return {"runs": [r.summary() for r in mgr.list_runs()]}


@app.get("/agents/{run_id}")
def get_agent(run_id: str) -> dict:
    mgr = get_agents()
    run = mgr.get(run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown run")
    return run.summary()


class AgentKillBody(BaseModel):
    reason: str = Field(default="killed by user", max_length=200)


@app.post("/agents/{run_id}/kill", dependencies=[Depends(require_bearer)])
async def kill_agent(run_id: str, body: AgentKillBody) -> dict:
    mgr = get_agents()
    if mgr.get(run_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown run")
    killed = await mgr.kill(run_id, reason=body.reason)
    audit.record("agents.kill", "user", {"run_id": run_id}, {"killed": killed}, ok=killed)
    return {"killed": killed}


def _voice_report(run_summary: dict) -> str:
    s = run_summary["status"]
    t = run_summary["type"]
    if s == RunStatus.DONE.value:
        return f"{t.capitalize()} agent finished. {run_summary['output'][:200]}"
    if s == RunStatus.FAILED.value:
        return f"{t.capitalize()} agent failed: {run_summary['error']}"
    if s == RunStatus.KILLED.value:
        return f"{t.capitalize()} agent killed: {run_summary['error']}"
    if s == RunStatus.NEEDS_CONFIRM.value:
        return f"{t.capitalize()} agent paused: {run_summary['error']}. Confirm to proceed."
    return f"{t.capitalize()} agent still {s}, {run_summary['elapsed_s']:.0f} seconds in."


@app.get("/agents/{run_id}/report")
def agent_report(run_id: str) -> dict:
    mgr = get_agents()
    run = mgr.get(run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown run")
    return {"text": _voice_report(run.summary())}


@app.get("/audit")
def get_audit(limit: int = 100) -> dict:
    return {"entries": audit.tail(get_db(), limit=limit)}


@app.get("/mission")
def get_mission(week: str | None = None) -> dict:
    conn = get_db()
    mission_eng.seed_mission_baseline(conn)
    series: dict[str, list[dict]] = {}
    for name in mission_eng.MISSION_METRIC_NAMES:
        history = metrics_store.history(conn, "mission", name, limit=52)
        series[name] = [
            {"value": p.value, "recorded_at": p.recorded_at}
            for p in reversed(history)
        ]
    target_week = week or _current_week_iso()
    choke = mission_eng.list_choke_points(conn, target_week)
    return {
        "week": target_week,
        "series": series,
        "choke_points": [
            {"rank": p.rank, "title": p.title, "note": p.note} for p in choke
        ],
    }


class ChokePointBody(BaseModel):
    week: str = Field(min_length=1)
    rank: int = Field(ge=1, le=3)
    title: str = Field(min_length=1, max_length=200)
    note: str | None = Field(default=None, max_length=1000)


@app.post("/mission/choke-points", dependencies=[Depends(require_bearer)])
def post_choke_point(body: ChokePointBody) -> dict:
    conn = get_db()
    try:
        cid = mission_eng.upsert_choke_point(
            conn, week=body.week, rank=body.rank, title=body.title, note=body.note
        )
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
    return {"id": cid}


def _current_week_iso() -> str:
    iso = datetime.now().isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


@app.get("/weekly/brief")
def weekly_brief() -> dict:
    summary = weekly_eng.render_weekly(get_db(), now=datetime.now())
    return {
        "week": summary.week,
        "text": summary.text,
        "shipped": summary.shipped,
        "slipped": summary.slipped,
        "choke_points": summary.choke_points,
        "deltas": summary.metric_deltas,
    }
