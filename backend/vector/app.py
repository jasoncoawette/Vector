from __future__ import annotations

from datetime import datetime
from typing import Any

import asyncio
import json

from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    Header,
    HTTPException,
    Request,
    Response,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import audit
from . import mocks as designkit_mocks
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
from pathlib import Path as _Path

GREETING_USER = "Jason"

app = FastAPI(title="Vector", version="0.1.0")
app.include_router(designkit_mocks.router)


def _cors_origins() -> list[str]:
    """Resolve the CORS allowlist from settings.

    Always includes the SvelteKit dev origin so `npm run dev` keeps
    working. Extra origins from VECTOR_CORS_ORIGINS (comma-separated)
    let a Tailscale-hosted MacBook hit the Mac mini backend by name."""
    base = ["http://127.0.0.1:5173", "http://localhost:5173"]
    base.extend(get_settings().cors_extra())
    return base


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)


def _loopback_host(host: str) -> bool:
    return host in ("127.0.0.1", "::1", "localhost", "")


@app.on_event("startup")
def _on_start() -> None:
    import logging as _logging

    from . import logging_setup

    logging_setup.configure()
    designkit_mocks.ensure_all_seeds()
    db = get_db()
    audit.set_sink(db)

    # Tailscale / LAN deploy guard: if the backend isn't on loopback we
    # need bearer auth, otherwise any host on the network can spawn agents
    # or write tools. Loud warning at startup, not a hard refusal — local
    # firewalls + Tailscale ACLs are a real defense too — but we want it
    # plain in the log.
    settings_now = get_settings()
    if not _loopback_host(settings_now.host) and not settings_now.backend_bearer:
        _logging.getLogger("vector.startup").error(
            "vector is bound to a non-loopback host but VECTOR_BACKEND_BEARER is "
            "unset; mutation endpoints will be open to anyone who can reach the port",
            extra={"host": settings_now.host},
        )
    # Crash recovery: any runs left in queued/running state belong to a
    # previous process that didn't shut down cleanly. Mark them as
    # interrupted so the /runs view shows the truth.
    from .store import runs as runs_store

    interrupted = runs_store.mark_interrupted_on_startup(db)
    _logging.getLogger("vector.startup").info(
        "vector started",
        extra={"interrupted_runs": interrupted},
    )
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
    """Liveness probe — cheap, always returns 200 if the event loop is
    answering. Use /health/deep for the dependency check."""
    return {"ok": True, "build": get_settings().build_hash}


@app.get("/health/deep")
def health_deep(response: Response) -> dict:
    """Readiness probe. Checks every dependency Vector needs to run:
    DB connectivity, integrity, workspace writability, audit sink.
    Returns 503 with a JSON body describing the first failure when
    any check fails so a watchdog can restart the process."""
    from .store import integrity as integrity_store

    checks: dict[str, dict] = {}
    overall_ok = True

    # 1. DB ping + integrity (cheap PRAGMA quick_check).
    try:
        db = get_db()
        row = db.execute("PRAGMA quick_check").fetchone()
        if row and row[0] == "ok":
            checks["db"] = {"ok": True}
        else:
            checks["db"] = {
                "ok": False,
                "reason": f"quick_check={row[0] if row else 'no row'}",
            }
            overall_ok = False
    except Exception as e:  # noqa: BLE001
        checks["db"] = {"ok": False, "reason": f"{type(e).__name__}: {e}"}
        overall_ok = False

    # 2. Workspace writable.
    try:
        ws = get_settings().workspace
        ws.mkdir(parents=True, exist_ok=True)
        probe = ws / ".health-probe"
        probe.write_text("ok")
        probe.unlink()
        checks["workspace"] = {"ok": True, "path": str(ws)}
    except Exception as e:  # noqa: BLE001
        checks["workspace"] = {"ok": False, "reason": f"{type(e).__name__}: {e}"}
        overall_ok = False

    # 3. Audit sink reachable (sink might be None pre-startup in tests).
    sink_ok = audit._sink is not None  # type: ignore[attr-defined]
    checks["audit"] = {"ok": sink_ok}
    if not sink_ok:
        overall_ok = False

    if not overall_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "ok": overall_ok,
        "checks": checks,
        "build": get_settings().build_hash,
    }


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
        # Keep reading WS frames until the socket closes. Mic-end ("end")
        # closes the audio iterator (via None on mic_queue) but pump_in
        # itself MUST stay alive so barge_in messages during TTS playback
        # still reach session.barge_in().
        mic_done = False
        try:
            while True:
                msg = await ws.receive()
                if msg["type"] == "websocket.disconnect":
                    if not mic_done:
                        await mic_queue.put(None)
                    return
                if "bytes" in msg and msg["bytes"] is not None:
                    if not mic_done:
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
                    if not mic_done:
                        await mic_queue.put(None)
                        mic_done = True
                    continue
                if kind == "barge_in":
                    session.barge_in()
        except WebSocketDisconnect:
            if not mic_done:
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
async def call_tool(body: ToolCallBody, reg: Registry = Depends(get_registry)) -> dict:
    try:
        result = await reg.acall(body.name, body.args)
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
    audit_rows = audit.by_trace(db, trace_id)
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


@app.get("/costs")
def get_costs(history_days: int = 14) -> dict:
    from .voice.costs import summarize

    s = get_settings()
    summary = summarize(
        get_db(),
        daily_budget_usd=s.daily_budget_usd,
        history_days=history_days,
    )
    return {
        "today_usd": round(summary.today_usd, 4),
        "today_runs": summary.today_runs,
        "week_usd": round(summary.week_usd, 4),
        "week_runs": summary.week_runs,
        "month_usd": round(summary.month_usd, 4),
        "month_runs": summary.month_runs,
        "daily_budget_usd": summary.daily_budget_usd,
        "over_budget_today": summary.over_budget_today,
        "daily": [
            {
                "day": d.day,
                "total_usd": round(d.total_usd, 4),
                "runs": d.runs,
                "by_type": {k: round(v, 4) for k, v in d.by_type.items()},
            }
            for d in summary.daily
        ],
        "by_tier": [
            {
                "tier": t.tier,
                "decisions": t.decisions,
                "total_usd": round(t.total_usd, 4),
                "mean_usd": round(t.mean_usd, 6),
            }
            for t in summary.by_tier
        ],
    }


# ---------------------------------------------------------------------
# Google OAuth bridge. Loopback consent flow + encrypted refresh-token
# storage. Endpoints land here, before the plans + static mount.
# ---------------------------------------------------------------------
from .deps import get_oauth_flow, get_token_store  # noqa: E402
from .google_oauth import OAuthError, SCOPES_CALENDAR, SCOPES_GMAIL_SEND  # noqa: E402


class OAuthStartBody(BaseModel):
    scopes: list[str] = Field(min_length=1, max_length=16)
    account: str = Field(default="default", max_length=200)


@app.post("/oauth/google/start", dependencies=[Depends(require_bearer)])
def oauth_google_start(body: OAuthStartBody) -> dict:
    """Begin the consent flow. Returns the URL to open in a browser."""
    flow = get_oauth_flow()
    if flow is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "google oauth not configured",
        )
    try:
        url = flow.start(body.scopes)
    except OAuthError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
    audit.record(
        "oauth.google.start",
        "user",
        {"scopes": body.scopes, "account": body.account},
        {"ok": True},
        ok=True,
    )
    return {"url": url, "account": body.account}


@app.get("/oauth/google/callback")
async def oauth_google_callback(
    code: str | None = None, state: str | None = None, error: str | None = None
) -> dict:
    """Google redirects here after the user grants access."""
    if error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"oauth error: {error}")
    if not code or not state:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "missing code or state")
    flow = get_oauth_flow()
    store = get_token_store()
    if flow is None or store is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "google oauth not configured",
        )
    try:
        token, pending = await flow.complete(code=code, state=state)
    except OAuthError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
    if not token.refresh_token:
        # Google only returns a refresh token on first grant or when
        # prompt=consent is set. Our flow sets prompt=consent so this
        # path is rare — but we surface it clearly if it happens.
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "no refresh token returned; revoke + retry the consent flow",
        )
    store.save(
        account="default",
        scopes=list(pending.scopes),
        refresh_token=token.refresh_token,
        access_token=token.access_token,
        expires_in=token.expires_in,
    )
    audit.record(
        "oauth.google.callback",
        "google",
        {"scopes": list(pending.scopes)},
        {"ok": True},
        ok=True,
    )
    return {"ok": True, "scopes": list(pending.scopes)}


@app.get("/oauth/google/status")
def oauth_google_status() -> dict:
    store = get_token_store()
    if store is None:
        return {"configured": False, "accounts": []}
    return {"configured": True, "accounts": store.list_accounts()}


@app.delete("/oauth/google/{account}", dependencies=[Depends(require_bearer)])
def oauth_google_revoke(account: str) -> dict:
    store = get_token_store()
    if store is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "google oauth not configured",
        )
    deleted = store.delete(account)
    audit.record(
        "oauth.google.revoke",
        "user",
        {"account": account},
        {"deleted": deleted},
        ok=deleted,
    )
    if not deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown account")
    return {"deleted": True}


# ---------------------------------------------------------------------
# Notebooks (Vector's NotebookLM-shape). Corpus -> grounded research
# answers with inline citations. Bearer-gated for writes; reads open.
# ---------------------------------------------------------------------
from .deps import (  # noqa: E402
    get_memory,
    get_notebook_brain,
    get_notebook_store,
)
from .notebook import research as notebook_research  # noqa: E402


class NotebookCreateBody(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=2000)


class NotebookSourceBody(BaseModel):
    handle: str = Field(min_length=1, max_length=500)
    kind: str = Field(default="text", max_length=20)
    text: str = Field(min_length=1, max_length=200_000)


class NotebookQueryBody(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    top_k: int = Field(default=6, ge=1, le=12)


def _serialize_notebook(nb) -> dict:
    return {
        "name": nb.name,
        "description": nb.description,
        "chunks": nb.chunks,
        "sources": [
            {
                "id": s.id,
                "handle": s.handle,
                "kind": s.kind,
                "chunks": s.chunks,
                "created_at": s.created_at,
            }
            for s in nb.sources
        ],
    }


@app.get("/notebooks")
def list_notebooks() -> dict:
    store = get_notebook_store()
    if store is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "notebook store unavailable"
        )
    return {"notebooks": [_serialize_notebook(nb) for nb in store.list_notebooks()]}


@app.post("/notebooks", dependencies=[Depends(require_bearer)])
def create_notebook(body: NotebookCreateBody) -> dict:
    store = get_notebook_store()
    if store is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "notebook store unavailable"
        )
    store.create(body.name, body.description)
    audit.record(
        "notebook.create", "user", {"name": body.name}, {"ok": True}, ok=True
    )
    return {"ok": True, "name": body.name}


@app.get("/notebooks/{name}")
def get_notebook(name: str) -> dict:
    store = get_notebook_store()
    if store is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "notebook store unavailable"
        )
    nb = store.get(name)
    if nb is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown notebook")
    return _serialize_notebook(nb)


@app.post("/notebooks/{name}/sources", dependencies=[Depends(require_bearer)])
def add_notebook_source(name: str, body: NotebookSourceBody) -> dict:
    store = get_notebook_store()
    if store is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "notebook store unavailable"
        )
    try:
        src = store.add_source(name, handle=body.handle, kind=body.kind, text=body.text)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
    audit.record(
        "notebook.add_source",
        "user",
        {"notebook": name, "handle": body.handle, "kind": body.kind},
        {"id": src.id, "chunks": src.chunks},
        ok=True,
    )
    return {
        "id": src.id,
        "handle": src.handle,
        "kind": src.kind,
        "chunks": src.chunks,
    }


@app.delete("/notebooks/{name}/sources/{source_id}", dependencies=[Depends(require_bearer)])
def remove_notebook_source(name: str, source_id: int) -> dict:
    store = get_notebook_store()
    if store is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "notebook store unavailable"
        )
    deleted = store.remove_source(source_id)
    if not deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown source")
    audit.record(
        "notebook.remove_source",
        "user",
        {"notebook": name, "source_id": source_id},
        {"deleted": True},
        ok=True,
    )
    return {"deleted": True}


@app.post("/notebooks/{name}/ask", dependencies=[Depends(require_bearer)])
async def ask_notebook(name: str, body: NotebookQueryBody) -> dict:
    store = get_notebook_store()
    if store is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "notebook store unavailable"
        )
    brain = get_notebook_brain()
    if brain is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "notebook brain unavailable (set ANTHROPIC_API_KEY)",
        )
    try:
        result = await notebook_research.answer(
            body.query,
            notebook=name,
            memory=get_memory(),
            notebook_store=store,
            brain=brain,
            top_k=body.top_k,
        )
    except ValueError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from e
    audit.record(
        "notebook.ask",
        "user",
        {"notebook": name, "query_len": len(body.query)},
        {"citations": len(result.citations), "cost_usd": result.cost_usd},
        ok=True,
    )
    return {
        "text": result.text,
        "citations": [
            {"source_id": c.source_id, "handle": c.handle, "snippet": c.snippet}
            for c in result.citations
        ],
        "cost_usd": result.cost_usd,
    }


# ---------------------------------------------------------------------
# Plans (DAG execution). Endpoints land here, before the static mount.
# ---------------------------------------------------------------------
from .deps import get_plans  # noqa: E402
from .plans.schema import PlanIn, build_plan  # noqa: E402
from .plans.types import PlanValidationError  # noqa: E402


@app.post("/plans", dependencies=[Depends(require_bearer)])
async def submit_plan(body: PlanIn, background: BackgroundTasks) -> dict:
    try:
        plan = build_plan(body)
    except PlanValidationError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
    runner = get_plans()
    # submit() registers the run synchronously and returns its coroutine.
    # We schedule the coroutine on FastAPI's BackgroundTasks so it lives
    # OUTSIDE the request's anyio task group — a raw asyncio.create_task
    # here would be cancelled the moment this handler returns.
    plan_run, coro = runner.submit(plan)

    async def _run_in_background() -> None:
        await coro

    background.add_task(_run_in_background)
    audit.record(
        "plans.submit",
        "user",
        {"goal": body.goal[:200], "steps": len(body.steps)},
        {"plan_id": plan.id},
        ok=True,
    )
    return plan_run.to_dict()


@app.get("/plans")
def list_plans() -> dict:
    return {"plans": [pr.to_dict() for pr in get_plans().list_runs()]}


@app.get("/plans/{plan_id}")
def get_plan(plan_id: str) -> dict:
    pr = get_plans().get(plan_id)
    if pr is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown plan")
    return pr.to_dict()


# ---------------------------------------------------------------------
# Static frontend bundle. Must be registered LAST so every /<api> route
# above wins the path match. Looks for frontend/build next to backend/;
# if it doesn't exist (fresh checkout, frontend not built yet), we skip
# the mount silently — backend still works for API + WebSocket clients.
# ---------------------------------------------------------------------
def _mount_static_frontend() -> None:
    from fastapi.staticfiles import StaticFiles

    here = _Path(__file__).resolve()
    # backend/vector/app.py -> backend/.. -> repo root -> frontend/build
    candidates = [
        here.parent.parent.parent / "frontend" / "build",
        here.parent.parent / "frontend" / "build",
    ]
    for build_dir in candidates:
        if build_dir.is_dir() and (build_dir / "index.html").exists():
            app.mount(
                "/",
                StaticFiles(directory=str(build_dir), html=True),
                name="frontend",
            )
            return


_mount_static_frontend()
