"""Persistence + audit gate for dynamic agent profiles.

Flow:
  prompt_engineer agent  →  produces AgentProfile JSON blob
  audit_blob(blob)        →  validates schema, tool allowlist, prompt
                              length, name collisions, cost cap
  insert(conn, profile)   →  persists to the `profiles` table
  load_all(conn)          →  pulls active rows on startup; registry
                              merges them with the built-ins

The audit gate is intentionally strict. A bad profile is a small fire;
a dangerous profile (file.delete, gmail.send, opus + no cost cap) can
be a big one.
"""
from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from typing import Any

from .profiles import AgentProfile, ProfileRegistry, VALID_TIERS

# Tool names that may NEVER appear in a dynamic profile's allowlist.
# These are dangerous-by-default (destructive or external-effect) and
# require human approval to grant — the built-in employees that need
# them are hardcoded so the grant is visible in code review.
FORBIDDEN_DYNAMIC_TOOLS: frozenset[str] = frozenset({
    "file.delete",
    "gmail.send",
    "gcal.create_event",
    "agents.spawn",
    "agents.fan_out",
    "plans.submit",
    # Shell-exec tools — dangerous-by-default. Forking subprocesses
    # bypasses the sandbox that gates every other tool, so only built-in
    # employees (self_healer) may have them in their allowlist.
    "shell.run_tests",
    "shell.run_lint",
    # Profile-admin tool — only the orchestrator may call this. Letting
    # a dynamic profile request it would let a freshly-minted agent mint
    # more profiles, which is a privilege-escalation path. Defense in
    # depth: even though only the orchestrator's allowlist names it,
    # forbid it here too.
    "profiles.audit_and_insert",
})

MAX_PROMPT_LEN = 4000
MAX_NAME_LEN = 64
MAX_COST_CAP = 5.0
MAX_STEP_BUDGET = 32


class ProfileAuditError(ValueError):
    """Raised when an audit check fails. The message is the rejection
    reason; pass it back to prompt_engineer so it can revise."""


@dataclass(frozen=True)
class StoredProfile:
    name: str
    system_prompt: str
    tools: frozenset[str]
    default_tier: str
    step_budget: int
    cost_cap_usd: float
    notes: str
    created_by: str | None
    created_at: float
    revoked_at: float | None

    def to_profile(self) -> AgentProfile:
        return AgentProfile(
            name=self.name,
            system_prompt=self.system_prompt,
            tools=self.tools,
            default_tier=self.default_tier,
            step_budget=self.step_budget,
            cost_cap_usd=self.cost_cap_usd,
            notes=self.notes,
            dynamic=True,
        )


def audit_blob(
    blob: dict[str, Any],
    *,
    built_in_names: frozenset[str],
    available_tools: frozenset[str],
) -> AgentProfile:
    """Validate a prompt_engineer-produced JSON blob. Returns the
    canonical AgentProfile on success; raises ProfileAuditError with a
    one-line reason on failure.

    `available_tools` is the live ToolRegistry's name set — we refuse
    profiles that reference tools the runtime can't serve.
    """
    if not isinstance(blob, dict):
        raise ProfileAuditError("blob must be a JSON object")

    required = {"name", "system_prompt", "tools", "default_tier",
                "step_budget", "cost_cap_usd", "notes"}
    missing = required - blob.keys()
    if missing:
        raise ProfileAuditError(f"missing required keys: {sorted(missing)}")

    name = blob["name"]
    if not isinstance(name, str) or not name:
        raise ProfileAuditError("name must be a non-empty string")
    if len(name) > MAX_NAME_LEN:
        raise ProfileAuditError(f"name longer than {MAX_NAME_LEN} chars")
    if not name.replace("_", "").isalnum():
        raise ProfileAuditError("name must be snake_case alphanumeric")
    if name in built_in_names:
        raise ProfileAuditError(f"name collides with built-in: {name}")

    prompt = blob["system_prompt"]
    if not isinstance(prompt, str) or not prompt.strip():
        raise ProfileAuditError("system_prompt must be a non-empty string")
    if len(prompt) > MAX_PROMPT_LEN:
        raise ProfileAuditError(
            f"system_prompt longer than {MAX_PROMPT_LEN} chars"
        )

    tools = blob["tools"]
    if not isinstance(tools, list):
        raise ProfileAuditError("tools must be a list of strings")
    tools_set = frozenset(tools)
    if len(tools_set) != len(tools):
        raise ProfileAuditError("tools contains duplicates")
    bad = [t for t in tools_set if not isinstance(t, str) or not t]
    if bad:
        raise ProfileAuditError("tools contains non-string or empty entries")
    forbidden = tools_set & FORBIDDEN_DYNAMIC_TOOLS
    if forbidden:
        raise ProfileAuditError(
            f"tools includes forbidden entries: {sorted(forbidden)}"
        )
    unknown = tools_set - available_tools
    if unknown:
        raise ProfileAuditError(
            f"tools includes unknown entries: {sorted(unknown)}"
        )

    tier = blob["default_tier"]
    if tier not in VALID_TIERS:
        raise ProfileAuditError(
            f"default_tier must be one of {sorted(VALID_TIERS)}"
        )

    step_budget = blob["step_budget"]
    if not isinstance(step_budget, int) or step_budget <= 0:
        raise ProfileAuditError("step_budget must be a positive integer")
    if step_budget > MAX_STEP_BUDGET:
        raise ProfileAuditError(f"step_budget exceeds {MAX_STEP_BUDGET}")

    cost_cap = blob["cost_cap_usd"]
    if not isinstance(cost_cap, (int, float)) or cost_cap <= 0:
        raise ProfileAuditError("cost_cap_usd must be a positive number")
    if cost_cap > MAX_COST_CAP:
        raise ProfileAuditError(f"cost_cap_usd exceeds {MAX_COST_CAP}")

    notes = blob.get("notes", "")
    if not isinstance(notes, str):
        raise ProfileAuditError("notes must be a string")

    return AgentProfile(
        name=name,
        system_prompt=prompt,
        tools=tools_set,
        default_tier=tier,
        step_budget=step_budget,
        cost_cap_usd=float(cost_cap),
        notes=notes,
        dynamic=True,
    )


def insert(
    conn: sqlite3.Connection,
    profile: AgentProfile,
    *,
    created_by: str | None = None,
) -> StoredProfile:
    """Persist an audited profile. Raises if the name already exists."""
    if not profile.dynamic:
        raise ValueError("only dynamic profiles are persisted; built-ins are code")
    now = time.time()
    conn.execute(
        "INSERT INTO profiles(name, system_prompt, tools_json, default_tier, "
        "step_budget, cost_cap_usd, notes, created_by, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            profile.name,
            profile.system_prompt,
            json.dumps(sorted(profile.tools)),
            profile.default_tier,
            profile.step_budget,
            profile.cost_cap_usd,
            profile.notes,
            created_by,
            now,
        ),
    )
    return StoredProfile(
        name=profile.name,
        system_prompt=profile.system_prompt,
        tools=profile.tools,
        default_tier=profile.default_tier,
        step_budget=profile.step_budget,
        cost_cap_usd=profile.cost_cap_usd,
        notes=profile.notes,
        created_by=created_by,
        created_at=now,
        revoked_at=None,
    )


def revoke(conn: sqlite3.Connection, name: str) -> bool:
    cur = conn.execute(
        "UPDATE profiles SET revoked_at = ? WHERE name = ? AND revoked_at IS NULL",
        (time.time(), name),
    )
    return cur.rowcount > 0


def audit_and_insert_and_register(
    blob: dict[str, Any],
    *,
    conn: sqlite3.Connection,
    registry: ProfileRegistry,
    available_tools: frozenset[str],
    created_by: str | None = None,
) -> tuple[bool, str, str | None]:
    """Audit a blob, persist it, and register it in one shot.

    Returns (ok, reason, name):
      ok=True  → persisted + registered; reason='loaded'; name=profile.name
      ok=False → audit/insert/register failed; reason=human-line; name=None

    Built-in names are pulled from the registry so the audit gate refuses
    collisions. Insert + register are wrapped in a try block; if either
    fails after audit passes, the row is left out of the registry and the
    error is returned (not raised) so the orchestrator can retry with a
    revised blob from prompt_engineer.
    """
    try:
        profile = audit_blob(
            blob,
            built_in_names=frozenset(registry.names()),
            available_tools=available_tools,
        )
    except ProfileAuditError as e:
        return (False, str(e), None)

    try:
        insert(conn, profile, created_by=created_by)
    except sqlite3.IntegrityError:
        return (False, f"name already in profiles table: {profile.name}", None)

    try:
        registry.register(profile)
    except ValueError as e:
        # In-memory collision (a dynamic of the same name was already
        # registered, or the name clashes with a built-in we didn't catch
        # in audit). The row was just inserted but isn't reachable through
        # the registry — revoke it so the DB stays consistent with the
        # registry's view of the world.
        revoke(conn, profile.name)
        return (False, str(e), None)

    return (True, "loaded", profile.name)


def load_active(conn: sqlite3.Connection) -> list[StoredProfile]:
    """All profiles not yet revoked. Used at app startup to merge into
    the in-memory registry alongside the hardcoded built-ins."""
    rows = conn.execute(
        "SELECT name, system_prompt, tools_json, default_tier, step_budget, "
        "cost_cap_usd, notes, created_by, created_at, revoked_at "
        "FROM profiles WHERE revoked_at IS NULL ORDER BY created_at ASC"
    ).fetchall()
    return [
        StoredProfile(
            name=r["name"],
            system_prompt=r["system_prompt"],
            tools=frozenset(json.loads(r["tools_json"])),
            default_tier=r["default_tier"],
            step_budget=int(r["step_budget"]),
            cost_cap_usd=float(r["cost_cap_usd"]),
            notes=r["notes"] or "",
            created_by=r["created_by"],
            created_at=float(r["created_at"]),
            revoked_at=(float(r["revoked_at"]) if r["revoked_at"] is not None else None),
        )
        for r in rows
    ]
