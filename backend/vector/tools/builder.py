from __future__ import annotations

import asyncio
import sqlite3
from typing import TYPE_CHECKING

from ..memory import MemoryStore
from .errors import ToolDenied
from .files import FileGuard
from .gcal import GCalClient
from .ggmail import GmailClient as GmailApiClient
from .maps import MapsClient
from .obsidian import ObsidianVault
from .registry import Registry, Tool
from .schemas import (
    AgentFanOutToolArgs,
    AgentSpawnToolArgs,
    AuditByTraceArgs,
    AuditTailArgs,
    EventsByTraceArgs,
    EventsRecentArgs,
    FileDeleteArgs,
    FileReadArgs,
    FileWriteArgs,
    GCalCreateArgs,
    GCalListArgs,
    GmailDraftArgs,
    GmailSendArgs,
    MapsDirectionsArgs,
    MapsGeocodeArgs,
    MapsPlacesArgs,
    MemoryAddArgs,
    MemorySearchArgs,
    ObsidianAppendArgs,
    ObsidianBacklinksArgs,
    ObsidianListArgs,
    ObsidianReadArgs,
    ObsidianSearchArgs,
    ObsidianWriteArgs,
    PlansSubmitToolArgs,
    ProfileAuditAndInsertArgs,
    RoutingStatsArgs,
    RunsGetArgs,
    RunsRecentArgs,
    ShellRunLintArgs,
    ShellRunTestsArgs,
)

if TYPE_CHECKING:
    from ..agents.manager import AgentManager
    from ..plans.executor import PlanRunner

from .shell import ShellRunner

# Which agent types get memory.search (read) vs memory.add (write).
# Code and tester get read-only; research / writer / security get both.
MEMORY_READ_TYPES = frozenset({"code", "tester", "research", "writer", "security"})
MEMORY_WRITE_TYPES = frozenset({"research", "writer", "security"})

# Obsidian vault: knowledge-base shape. Read tools go to anything that
# could benefit from prior notes; write tools only to research + writer
# so code / tester / security can't accidentally pollute the vault.
OBSIDIAN_READ_TYPES = frozenset({"code", "tester", "research", "writer", "security"})
OBSIDIAN_WRITE_TYPES = frozenset({"research", "writer"})

# Google Maps: productivity-shaped. Only research + writer agents
# really need it (researching a route, drafting "meet me at" text).
# Code / tester / security have no business hitting the maps API.
MAPS_TYPES = frozenset({"research", "writer"})

# Google Calendar + Gmail: productivity. Same gating as Maps; both go
# through ConfirmGate for any mutation (gcal.create_event, gmail.send).
GCAL_TYPES = frozenset({"research", "writer"})
GMAIL_TYPES = frozenset({"research", "writer"})


def _add_file_tools(reg: Registry, guard: FileGuard) -> None:
    reg.register(
        Tool(
            name="file.read",
            schema=FileReadArgs,
            handler=lambda a: guard.read(a.path),
            description="Read a text file inside scope.",
        )
    )
    reg.register(
        Tool(
            name="file.write",
            schema=FileWriteArgs,
            handler=lambda a: guard.write(a.path, a.content, confirm=a.confirm),
            description="Write to workspace; outside workspace requires confirm.",
        )
    )

    def _delete(args: FileDeleteArgs):
        if args.confirm_token:
            return guard.confirm_delete(args.path, args.confirm_token)
        return guard.request_delete(args.path)

    reg.register(
        Tool(
            name="file.delete",
            schema=FileDeleteArgs,
            handler=_delete,
            description="Two-step delete. First call returns a confirm token.",
        )
    )


def _add_memory_search(reg: Registry, memory: MemoryStore) -> None:
    reg.register(
        Tool(
            name="memory.search",
            schema=MemorySearchArgs,
            handler=lambda a: [
                {
                    "id": m.id,
                    "kind": m.kind,
                    "text": m.text,
                    "score": m.score,
                    "recorded_at": m.recorded_at,
                }
                for m in memory.search(a.query, kind=a.kind, k=a.k)
            ],
            description="Recall prior memories by semantic similarity.",
        )
    )


def _add_memory_add(reg: Registry, memory: MemoryStore) -> None:
    reg.register(
        Tool(
            name="memory.add",
            schema=MemoryAddArgs,
            handler=lambda a: {"id": memory.add(a.kind, a.text, a.meta)},
            description="Persist a new memory for later recall.",
        )
    )


def _add_obsidian_read(reg: Registry, vault: ObsidianVault) -> None:
    reg.register(
        Tool(
            name="obsidian.list",
            schema=ObsidianListArgs,
            handler=lambda _a: {"notes": vault.list_notes()},
            description="List every note title in the Obsidian vault.",
        )
    )
    reg.register(
        Tool(
            name="obsidian.read",
            schema=ObsidianReadArgs,
            handler=lambda a: vault.read(a.title),
            description="Read one Obsidian note by title (or folder/title).",
        )
    )
    reg.register(
        Tool(
            name="obsidian.search",
            schema=ObsidianSearchArgs,
            handler=lambda a: [
                {
                    "title": h.title,
                    "snippet": h.snippet,
                    "line": h.line,
                }
                for h in vault.search(a.query, k=a.k)
            ],
            description="Substring search across the vault. Returns title + snippet.",
        )
    )
    reg.register(
        Tool(
            name="obsidian.backlinks",
            schema=ObsidianBacklinksArgs,
            handler=lambda a: {"backlinks": vault.backlinks(a.title)},
            description="Notes that link to [[title]] via wiki-link syntax.",
        )
    )


def _add_obsidian_write(reg: Registry, vault: ObsidianVault) -> None:
    reg.register(
        Tool(
            name="obsidian.write",
            schema=ObsidianWriteArgs,
            handler=lambda a: vault.write(a.title, a.body),
            description="Create or overwrite an Obsidian note.",
        )
    )
    reg.register(
        Tool(
            name="obsidian.append",
            schema=ObsidianAppendArgs,
            handler=lambda a: vault.append(a.title, a.body),
            description="Append to an existing note (creates it if missing).",
        )
    )


def _add_gcal_tools(reg: Registry, gcal: GCalClient) -> None:
    reg.register(
        Tool(
            name="gcal.list_upcoming",
            schema=GCalListArgs,
            handler=lambda a: gcal.list_upcoming(
                within_hours=a.within_hours, max_results=a.max_results
            ),
            description="List Google Calendar events in the next within_hours window.",
        )
    )

    def _create(args: GCalCreateArgs):
        return gcal.create_event(
            summary=args.summary,
            start_iso=args.start_iso,
            end_iso=args.end_iso,
            location=args.location,
            description=args.description,
            confirm_token=args.confirm_token,
        )

    reg.register(
        Tool(
            name="gcal.create_event",
            schema=GCalCreateArgs,
            handler=_create,
            description=(
                "Create a calendar event. First call returns a needs_confirm token; "
                "second call with confirm_token actually writes."
            ),
        )
    )


def _add_gmail_tools(reg: Registry, gmail: GmailApiClient) -> None:
    reg.register(
        Tool(
            name="gmail.draft",
            schema=GmailDraftArgs,
            handler=lambda a: gmail.draft(to=a.to, subject=a.subject, body=a.body),
            description="Create a Gmail draft (no send). Safe for preview.",
        )
    )

    def _send(args: GmailSendArgs):
        return gmail.send(
            to=args.to,
            subject=args.subject,
            body=args.body,
            confirm_token=args.confirm_token,
        )

    reg.register(
        Tool(
            name="gmail.send",
            schema=GmailSendArgs,
            handler=_send,
            description=(
                "Send a Gmail message. First call returns a needs_confirm token; "
                "second call with confirm_token actually sends."
            ),
        )
    )


def _add_shell_tools(reg: Registry, runner: ShellRunner) -> None:
    """Register the sandboxed test + lint subprocess tools.

    These are the FIRST shell-execution tools in the codebase and are
    in FORBIDDEN_DYNAMIC_TOOLS — only built-in employees (self_healer)
    can have them in their allowlist.
    """
    reg.register(
        Tool(
            name="shell.run_tests",
            schema=ShellRunTestsArgs,
            handler=lambda a: runner.run_tests(
                path=a.path, framework=a.framework
            ).to_dict(),
            description=(
                "Run the project's test suite (pytest or vitest) inside the "
                "repo with a hard timeout and minimal env. Returns exit_code, "
                "stdout/stderr tails, and pytest passed/failed counts."
            ),
        )
    )
    reg.register(
        Tool(
            name="shell.run_lint",
            schema=ShellRunLintArgs,
            handler=lambda a: runner.run_lint(
                path=a.path, tool=a.tool
            ).to_dict(),
            description=(
                "Run a linter (ruff or svelte-check) inside the repo with a "
                "hard timeout and minimal env. Returns exit_code + output."
            ),
        )
    )


def _add_maps_tools(reg: Registry, maps: MapsClient) -> None:
    reg.register(
        Tool(
            name="maps.geocode",
            schema=MapsGeocodeArgs,
            handler=lambda a: maps.geocode(a.address),  # returns Awaitable
            description="Resolve an address to lat/lng + canonical components.",
        )
    )
    reg.register(
        Tool(
            name="maps.directions",
            schema=MapsDirectionsArgs,
            handler=lambda a: maps.directions(a.origin, a.destination, mode=a.mode),
            description="Routing between two addresses with distance + ETA.",
        )
    )
    reg.register(
        Tool(
            name="maps.places",
            schema=MapsPlacesArgs,
            handler=lambda a: maps.places(a.query, near=a.near, k=a.k),
            description="Places text search; optional locationBias via near='lat,lng'.",
        )
    )


def _serialize_event_obj(e) -> dict:
    """Mirror of app._serialize_event for the debug tools. Kept local
    so the tools/ package doesn't pull in vector.app."""
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


def _serialize_stored_run_obj(r) -> dict:
    """Mirror of app._serialize_stored_run. Output is truncated so the
    tool reply stays small enough for an LLM context window."""
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


def _serialize_tier_summary(s) -> dict:
    """TierSummary dataclass → JSON-safe dict."""
    return {
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


def _add_debug_tools(reg: Registry, db: sqlite3.Connection) -> None:
    """Read-only telemetry tools for the debugger profile.

    All seven tools wrap existing store-level functions and return
    JSON-serializable dicts/lists. None of them mutate, so they're
    safe to expose under SQLite WAL with concurrent readers.
    """
    from .. import audit
    from ..store import events as events_store
    from ..store import runs as runs_store
    from ..voice.routing_stats import per_tier_summary

    reg.register(
        Tool(
            name="events.recent",
            schema=EventsRecentArgs,
            handler=lambda a: [
                _serialize_event_obj(e)
                for e in events_store.recent(db, limit=a.limit)
            ],
            description="Most recent events across all traces, newest first.",
        )
    )
    reg.register(
        Tool(
            name="events.by_trace",
            schema=EventsByTraceArgs,
            handler=lambda a: [
                _serialize_event_obj(e)
                for e in events_store.by_trace(db, a.trace_id)
            ],
            description="All events for one trace_id, oldest first.",
        )
    )
    reg.register(
        Tool(
            name="audit.tail",
            schema=AuditTailArgs,
            handler=lambda a: audit.tail(db, limit=a.limit),
            description="Most recent audit_log rows, newest first.",
        )
    )
    reg.register(
        Tool(
            name="audit.by_trace",
            schema=AuditByTraceArgs,
            handler=lambda a: audit.by_trace(db, a.trace_id),
            description="All audit_log rows for one trace_id, oldest first.",
        )
    )
    reg.register(
        Tool(
            name="runs.recent",
            schema=RunsRecentArgs,
            handler=lambda a: [
                _serialize_stored_run_obj(r)
                for r in runs_store.recent(db, limit=a.limit, status=a.status)
            ],
            description="Persisted run history; optional status filter.",
        )
    )

    def _runs_get(a: RunsGetArgs):
        r = runs_store.get(db, a.run_id)
        return _serialize_stored_run_obj(r) if r is not None else {}

    reg.register(
        Tool(
            name="runs.get",
            schema=RunsGetArgs,
            handler=_runs_get,
            description="Fetch one run by id, or {} if not found.",
        )
    )
    reg.register(
        Tool(
            name="routing.stats",
            schema=RoutingStatsArgs,
            handler=lambda _a: {
                "tiers": [_serialize_tier_summary(s) for s in per_tier_summary(db)]
            },
            description="Per-tier routing bandit + outcome summary.",
        )
    )


def _add_orchestration_tools(
    reg: Registry,
    manager: "AgentManager",
    plans_runner: "PlanRunner",
) -> None:
    """Register the agents.spawn / agents.fan_out / plans.submit tools.

    Profile names are resolved through the profile registry so aliases
    like 'code' still work. Plan submission schedules the runner's
    coroutine as a background task — keeping the tool call fast while
    the plan executes off the request path.
    """
    from ..agents.profiles import default_registry
    from ..agents.types import AgentSpec
    from ..plans.schema import PlanIn, build_plan

    def _spec_from(args: AgentSpawnToolArgs) -> AgentSpec:
        try:
            resolved = default_registry().resolve(args.name)
        except KeyError as e:
            raise ToolDenied(f"unknown agent profile: {args.name}") from e
        return AgentSpec(
            type=resolved,
            prompt=args.prompt,
            files=frozenset(args.files),
            cost_cap_usd=args.cost_cap_usd,
            timeout_s=args.timeout_s,
            success_criteria=args.success_criteria,
            max_attempts=args.max_attempts,
        )

    async def _spawn(args: AgentSpawnToolArgs) -> dict:
        spec = _spec_from(args)
        run = await manager.spawn(spec)
        return {"id": run.id, "name": spec.type, "status": run.status.value}

    async def _fan_out(args: AgentFanOutToolArgs) -> dict:
        specs = [_spec_from(s) for s in args.specs]
        runs = await manager.fan_out(specs)
        return {
            "runs": [
                {"id": r.id, "name": r.spec.type, "status": r.status.value}
                for r in runs
            ]
        }

    async def _submit_plan(args: PlansSubmitToolArgs) -> dict:
        plan = build_plan(PlanIn(**args.model_dump()))
        plan_run, coro = plans_runner.submit(plan)
        asyncio.create_task(coro)
        return {"plan_id": plan.id, "status": plan_run.status.value}

    reg.register(
        Tool(
            name="agents.spawn",
            schema=AgentSpawnToolArgs,
            handler=_spawn,
            description=(
                "Spawn one sub-agent by profile name (alias OK). "
                "Returns the new run id + status."
            ),
        )
    )
    reg.register(
        Tool(
            name="agents.fan_out",
            schema=AgentFanOutToolArgs,
            handler=_fan_out,
            description=(
                "Spawn multiple sub-agents in one call. Manager's parallel "
                "cap and file-conflict guard still apply."
            ),
        )
    )
    reg.register(
        Tool(
            name="plans.submit",
            schema=PlansSubmitToolArgs,
            handler=_submit_plan,
            description=(
                "Submit a multi-step Plan (DAG of agent steps). Runs in "
                "the background; returns the plan id immediately."
            ),
        )
    )


def _add_profile_admin_tools(reg: Registry, db: sqlite3.Connection) -> None:
    """Register profiles.audit_and_insert — the orchestrator's bridge from
    prompt_engineer's JSON output to a persisted + registered AgentProfile.

    The handler is sync. It returns {ok, reason, name} for every outcome
    (including bad JSON) so the orchestrator can route the reason back
    to prompt_engineer and ask for a revision instead of stalling on a
    raised exception.

    Lazy imports keep tools/ free of agent-package + json import overhead
    on cold paths that don't touch this tool.
    """
    def _audit_and_insert(args: ProfileAuditAndInsertArgs) -> dict:
        import json

        from ..agents.profile_store import audit_and_insert_and_register
        from ..agents.profiles import default_registry

        try:
            blob = json.loads(args.blob_json)
        except json.JSONDecodeError as e:
            return {"ok": False, "reason": f"invalid JSON: {e}", "name": None}
        ok, reason, name = audit_and_insert_and_register(
            blob,
            conn=db,
            registry=default_registry(),
            available_tools=frozenset(reg.names()),
        )
        return {"ok": ok, "reason": reason, "name": name}

    reg.register(
        Tool(
            name="profiles.audit_and_insert",
            schema=ProfileAuditAndInsertArgs,
            handler=_audit_and_insert,
            description=(
                "Audit a prompt_engineer-produced AgentProfile JSON blob, "
                "persist it, and register it. Returns {ok, reason, name}; "
                "ok=false carries a human-readable reason for the engineer."
            ),
        )
    )


def build_default_registry(guard: FileGuard) -> Registry:
    reg = Registry()
    _add_file_tools(reg, guard)
    return reg


def _build_master_registry(
    *,
    guard: FileGuard,
    memory: MemoryStore | None,
    obsidian: ObsidianVault | None,
    maps: MapsClient | None,
    gcal: GCalClient | None,
    gmail: GmailApiClient | None,
    db: sqlite3.Connection | None = None,
    shell: ShellRunner | None = None,
    manager: "AgentManager | None" = None,
    plans_runner: "PlanRunner | None" = None,
    profile_admin: bool = False,
) -> Registry:
    """Register every tool the runtime can currently serve.

    Pure side-effect helper: doesn't care about agent gating. The
    profile-aware filter happens in build_registry_for() below.

    `profile_admin=True` AND `db is not None` registers the
    profiles.audit_and_insert tool. We can't gate on db alone — the
    debug tools already do that, and we don't want every db caller to
    receive admin tools. Only the orchestrator's master registry sets
    the flag (see deps._registry_factory).
    """
    reg = Registry()
    _add_file_tools(reg, guard)
    if memory is not None:
        _add_memory_search(reg, memory)
        _add_memory_add(reg, memory)
    if obsidian is not None:
        _add_obsidian_read(reg, obsidian)
        _add_obsidian_write(reg, obsidian)
    if maps is not None:
        _add_maps_tools(reg, maps)
    if gcal is not None:
        _add_gcal_tools(reg, gcal)
    if gmail is not None:
        _add_gmail_tools(reg, gmail)
    if db is not None:
        _add_debug_tools(reg, db)
    if shell is not None:
        _add_shell_tools(reg, shell)
    if manager is not None and plans_runner is not None:
        _add_orchestration_tools(reg, manager, plans_runner)
    if profile_admin and db is not None:
        _add_profile_admin_tools(reg, db)
    return reg


def _filter_registry(master: Registry, allowlist: frozenset[str]) -> Registry:
    """Return a new Registry containing only tools whose names appear in
    `allowlist`. Tools requested by allowlist but not present in master
    are silently dropped — the audit trail in the caller logs missing
    tools at startup, not on every dispatch."""
    out = Registry()
    for name in allowlist:
        if name not in master._tools:  # noqa: SLF001 — same package
            continue
        out.register(master._tools[name])  # noqa: SLF001
    return out


def build_registry_for(
    agent_type: str | None,
    *,
    guard: FileGuard,
    memory: MemoryStore | None = None,
    obsidian: ObsidianVault | None = None,
    maps: MapsClient | None = None,
    gcal: GCalClient | None = None,
    gmail: GmailApiClient | None = None,
    db: sqlite3.Connection | None = None,
    shell: ShellRunner | None = None,
    manager: "AgentManager | None" = None,
    plans_runner: "PlanRunner | None" = None,
    profile_admin: bool = False,
) -> Registry:
    """Return a registry scoped to one agent profile's tool allowlist.

    The profile registry (vector.agents.profiles) is the source of truth
    for which tools each agent can call. Legacy callers passing the old
    enum names ('code', 'research') are routed through the alias map.

    agent_type=None → master registry (every available tool). Used by
    the voice brain when it isn't acting as a specific employee.

    `profile_admin=True` enables registration of the
    profiles.audit_and_insert tool (orchestrator-only; deps wires it).
    """
    master = _build_master_registry(
        guard=guard, memory=memory, obsidian=obsidian,
        maps=maps, gcal=gcal, gmail=gmail, db=db, shell=shell,
        manager=manager, plans_runner=plans_runner,
        profile_admin=profile_admin,
    )
    if agent_type is None:
        return master

    # Lazy import: profile registry imports prompts, which is heavy.
    from ..agents.profiles import default_registry

    try:
        profile = default_registry().get(agent_type)
    except KeyError:
        # Unknown profile — be permissive (return master). Manager-level
        # validation should have already rejected the spawn; this branch
        # only fires for test fixtures with synthetic types.
        return master

    return _filter_registry(master, profile.tools)
