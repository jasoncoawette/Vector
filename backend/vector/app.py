from __future__ import annotations

from datetime import datetime
from typing import Any

import asyncio
import json

from fastapi import (
    Depends,
    FastAPI,
    Header,
    HTTPException,
    Request,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import audit
from .agents.types import AgentSpec, AgentType, RunStatus
from .auth import check_ws_bearer, require_bearer
from .store import events as events_store
from .tracing import trace
from .voice.session import VoiceEvent, VoiceState
from .config import get_settings
from .deps import get_agents, get_db, new_voice_session
from .engine import brief as brief_mod
from .engine import mission as mission_eng
from .engine import picker, review
from .engine import weekly as weekly_eng
from .store import metrics as metrics_store
from .store import tasks as tasks_repo
from .tools.builder import build_default_registry
from .tools.errors import NeedsConfirm, ToolDenied, ToolError
from .tools.files import FileGuard
from .voice.routing_stats import per_tier_summary, recent_decisions
from .webhooks import handle_linear_event, verify_linear_signature
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
    db = get_db()
    audit.set_sink(db)
    # Crash recovery: any runs left in queued/running state belong to a
    # previous process that didn't shut down cleanly. Mark them as
    # interrupted so the /runs view shows the truth.
    from .store import runs as runs_store

    interrupted = runs_store.mark_interrupted_on_startup(db)
    if interrupted:
        from .store import events as events_store

        try:
            events_store.emit(
                db, "startup_recovery", meta={"interrupted_runs": interrupted}
            )
        except Exception:  # noqa: BLE001
            pass


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


def _event_to_json(e: VoiceEvent) -> dict:
    return {
        "kind": e.kind,
        "state": e.state.value if isinstance(e.state, VoiceState) else None,
        "text": e.text,
        "error": e.error,
    }


@app.websocket("/voice/stream")
async def voice_stream(ws: WebSocket) -> None:
    if not await check_ws_bearer(ws):
        return
    await ws.accept()
    # Bind a trace_id for this WebSocket connection. All audit, routing,
    # and events rows emitted during the turn(s) inherit it.
    with trace() as trace_id:
        try:
            events_store.emit(get_db(), "turn_start", meta={"trace_id": trace_id})
        except Exception:  # noqa: BLE001 — never fail the turn over telemetry
            pass
        await _voice_stream_loop(ws)


async def _voice_stream_loop(ws: WebSocket) -> None:
    session = new_voice_session()
    mic_queue: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=64)

    async def mic_iter():
        while True:
            item = await mic_queue.get()
            if item is None:
                return
            yield item

    async def pump_in() -> None:
        try:
            while True:
                msg = await ws.receive()
                if msg["type"] == "websocket.disconnect":
                    await mic_queue.put(None)
                    return
                if "bytes" in msg and msg["bytes"] is not None:
                    await mic_queue.put(msg["bytes"])
                    continue
                text = msg.get("text")
                if not text:
                    continue
                try:
                    data = json.loads(text)
                except json.JSONDecodeError:
                    continue
                kind = data.get("type")
                if kind == "end":
                    await mic_queue.put(None)
                    return
                if kind == "barge_in":
                    session.barge_in()
        except WebSocketDisconnect:
            await mic_queue.put(None)

    pump_task = asyncio.create_task(pump_in())
    try:
        async for event in session.turn(mic_iter()):
            if event.kind == "audio" and event.audio is not None:
                await ws.send_bytes(event.audio)
            else:
                await ws.send_json(_event_to_json(event))
    except WebSocketDisconnect:
        pass
    finally:
        await mic_queue.put(None)
        pump_task.cancel()
        try:
            await pump_task
        except (asyncio.CancelledError, Exception):
            pass
        try:
            await ws.close()
        except RuntimeError:
            pass


@app.get("/tools")
def list_tools(reg: Registry = Depends(get_registry)) -> dict:
    return {"tools": reg.list()}


class ToolCallBody(BaseModel):
    name: str = Field(min_length=1)
    args: dict[str, Any] = Field(default_factory=dict)
    caller: str = "user"


@app.post("/tools/call", dependencies=[Depends(require_bearer)])
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


@app.post("/daily/review", dependencies=[Depends(require_bearer)])
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


@app.post("/metrics", dependencies=[Depends(require_bearer)])
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


@app.post("/tasks", dependencies=[Depends(require_bearer)])
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
    success_criteria: str | None = Field(default=None, max_length=2000)
    max_attempts: int = Field(default=3, ge=1, le=5)


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
        success_criteria=body.success_criteria,
        max_attempts=body.max_attempts,
    )
    with trace() as trace_id:
        run = await mgr.spawn(spec)
        try:
            events_store.emit(
                get_db(),
                "agent_spawn_request",
                run_id=run.id,
                meta={"type": body.type, "trace_id": trace_id},
            )
        except Exception:  # noqa: BLE001
            pass
        audit.record(
            "agents.spawn", "user", body.model_dump(), {"id": run.id}, ok=True
        )
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


@app.post("/agents/pause", dependencies=[Depends(require_bearer)])
async def pause_agents() -> dict:
    mgr = get_agents()
    await mgr.pause()
    audit.record("agents.pause", "user", {}, {"paused": True}, ok=True)
    return {"paused": True}


@app.post("/agents/resume", dependencies=[Depends(require_bearer)])
async def resume_agents() -> dict:
    mgr = get_agents()
    await mgr.resume()
    audit.record("agents.resume", "user", {}, {"paused": False}, ok=True)
    return {"paused": False}


class RefocusBody(BaseModel):
    prompt: str = Field(min_length=1, max_length=8000)


@app.post("/agents/{run_id}/refocus", dependencies=[Depends(require_bearer)])
async def refocus_agent(run_id: str, body: RefocusBody) -> dict:
    mgr = get_agents()
    new_run = await mgr.refocus(run_id, body.prompt)
    if new_run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown run")
    audit.record(
        "agents.refocus",
        "user",
        {"old": run_id, "prompt_len": len(body.prompt)},
        {"new": new_run.id},
        ok=True,
    )
    return new_run.summary()


class FanOutBody(BaseModel):
    specs: list[AgentSpawnBody] = Field(min_length=1, max_length=8)


@app.post("/agents/fan-out", dependencies=[Depends(require_bearer)])
async def fan_out_agents(body: FanOutBody) -> dict:
    mgr = get_agents()
    specs = [
        AgentSpec(
            type=s.type,
            prompt=s.prompt,
            files=frozenset(s.files),
            fallback_prompt=s.fallback_prompt,
            cost_cap_usd=s.cost_cap_usd,
            timeout_s=s.timeout_s,
            success_criteria=s.success_criteria,
            max_attempts=s.max_attempts,
        )
        for s in body.specs
    ]
    with trace() as trace_id:
        runs = await mgr.fan_out(specs)
        try:
            events_store.emit(
                get_db(),
                "agent_fan_out",
                meta={
                    "trace_id": trace_id,
                    "count": len(specs),
                    "ids": [r.id for r in runs],
                },
            )
        except Exception:  # noqa: BLE001
            pass
        audit.record(
            "agents.fan_out",
            "user",
            {"count": len(specs), "types": [s.type for s in body.specs]},
            {"ids": [r.id for r in runs]},
            ok=True,
        )
    return {"runs": [r.summary() for r in runs]}


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


@app.post("/webhooks/linear")
async def linear_webhook(
    request: Request,
    linear_signature: str | None = Header(default=None, alias="Linear-Signature"),
) -> dict:
    secret = get_settings().linear_webhook_secret
    if not secret:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "webhook not configured")
    # Bind a trace_id for this webhook delivery so audit + events
    # rows can be joined back to the inbound POST.
    with trace():
        return await _process_linear_webhook(request, linear_signature, secret)


async def _process_linear_webhook(
    request: Request, linear_signature: str | None, secret: str
) -> dict:
    body = await request.body()
    try:
        verify_linear_signature(body, signature=linear_signature, secret=secret)
    except ValueError as e:
        audit.record(
            "linear.webhook", "linear", {}, {"reason": str(e)}, ok=False
        )
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(e)) from e
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "bad json") from e
    result = handle_linear_event(get_db(), payload)
    audit.record("linear.webhook", "linear", {"action": payload.get("action")}, result, ok=result.get("ok", False))
    return result


@app.get("/routing/stats")
def routing_stats() -> dict:
    return {
        "tiers": [
            {
                "tier": s.tier,
                "decisions": s.decisions,
                "successes": s.successes,
                "failures": s.failures,
                "pending": s.pending,
                "mean_cost_usd": s.mean_cost_usd,
                "success_rate": s.success_rate,
                "alpha": s.alpha,
                "beta": s.beta,
                "trials": s.trials,
                "mean_reward": s.mean_reward,
            }
            for s in per_tier_summary(get_db())
        ]
    }


@app.get("/routing/log")
def routing_log(limit: int = 100) -> dict:
    return {"entries": recent_decisions(get_db(), limit=limit)}


def _serialize_event(e) -> dict:
    return {
        "id": e.id,
        "ts": e.ts,
        "trace_id": e.trace_id,
        "run_id": e.run_id,
        "kind": e.kind,
        "cost_delta": e.cost_delta,
        "latency_ms": e.latency_ms,
        "meta": e.meta,
    }


@app.get("/events")
def get_events(limit: int = 200) -> dict:
    return {
        "events": [_serialize_event(e) for e in events_store.recent(get_db(), limit=limit)]
    }


@app.get("/trace/{trace_id}")
def get_trace(trace_id: str) -> dict:
    """Reconstruct a full chain by trace_id: events + audit rows + routing."""
    db = get_db()
    events = events_store.by_trace(db, trace_id)
    audit_rows = [
        dict(r)
        for r in db.execute(
            "SELECT ts, tool, caller, ok, reason FROM audit_log "
            "WHERE trace_id = ? ORDER BY ts ASC",
            (trace_id,),
        ).fetchall()
    ]
    routing_rows = [
        dict(r)
        for r in db.execute(
            "SELECT ts, agent_type, tier, model, score, source, outcome, cost_usd "
            "FROM routing_log WHERE trace_id = ? ORDER BY ts ASC",
            (trace_id,),
        ).fetchall()
    ]
    return {
        "trace_id": trace_id,
        "events": [_serialize_event(e) for e in events],
        "audit": audit_rows,
        "routing": routing_rows,
    }


def _serialize_stored_run(r) -> dict:
    return {
        "id": r.id,
        "trace_id": r.trace_id,
        "type": r.type,
        "prompt": r.prompt[:200],
        "files": r.files,
        "status": r.status,
        "output": r.output[:4000],
        "error": r.error,
        "cost_usd": round(r.cost_usd, 4),
        "fallback_used": r.fallback_used,
        "attempts_used": r.attempts_used,
        "max_attempts": r.max_attempts,
        "last_verifier_reason": r.last_verifier_reason,
        "queued_at": r.queued_at,
        "started_at": r.started_at,
        "ended_at": r.ended_at,
        "updated_at": r.updated_at,
    }


@app.get("/runs")
def list_persisted_runs(limit: int = 100, status: str | None = None) -> dict:
    """Read agent-run history from the persistent store. Unlike
    /agents, this survives backend restarts."""
    from .store import runs as runs_store

    rows = runs_store.recent(get_db(), limit=limit, status=status)
    return {"runs": [_serialize_stored_run(r) for r in rows]}


@app.get("/runs/{run_id}")
def get_persisted_run(run_id: str) -> dict:
    from .store import runs as runs_store

    r = runs_store.get(get_db(), run_id)
    if r is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown run")
    return _serialize_stored_run(r)
