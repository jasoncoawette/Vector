"""Agent profile registry.

An AgentProfile is the unit of "what an agent is": a name, a trained
system prompt, an allowlist of tool names, a routing hint, a few
guardrails. Adding a new employee = one AgentProfile literal in
built_in_profiles(). No edits to enums, frozensets, or dispatchers.

Naming
------
Canonical names are snake_case (developer, self_healer, prompt_engineer).
Aliases provide backward compat for the original AgentType enum:
   code     → developer
   research → researcher
Anywhere a profile name is accepted, an alias resolves to the canonical
name first.

Tool allowlists
---------------
The allowlist names tools by string. The actual ToolRegistry only
exposes tools the runtime can serve (which depends on which clients are
configured — Gmail needs OAuth, Maps needs a key, etc.). So the
effective tool set for an agent is `profile.tools ∩ registry.names()`.
The build_registry_for helper takes care of that intersection.
"""
from __future__ import annotations

from dataclasses import dataclass, field


VALID_TIERS = frozenset({"haiku", "sonnet", "opus"})


@dataclass(frozen=True)
class AgentProfile:
    """Everything the orchestrator + executor need to spawn an agent.

    Profiles are *data*. They live in the registry; nothing in the
    runtime should hardcode a profile by name except the orchestrator
    deciding who to delegate to.
    """

    name: str
    system_prompt: str
    tools: frozenset[str] = frozenset()
    default_tier: str = "sonnet"
    step_budget: int = 12
    cost_cap_usd: float = 1.0
    notes: str = ""
    # Dynamic profiles are produced at runtime (by prompt_engineer) and
    # persisted to the `profiles` table after audit. Built-in employees
    # have dynamic=False.
    dynamic: bool = False

    def __post_init__(self) -> None:
        if not self.name or not self.name.replace("_", "").isalnum():
            raise ValueError(
                f"profile name must be snake_case alphanumeric: {self.name!r}"
            )
        if self.default_tier not in VALID_TIERS:
            raise ValueError(
                f"default_tier must be one of {sorted(VALID_TIERS)}: "
                f"{self.default_tier!r}"
            )
        if self.step_budget <= 0 or self.step_budget > 64:
            raise ValueError(f"step_budget out of range: {self.step_budget}")
        if self.cost_cap_usd <= 0 or self.cost_cap_usd > 50:
            raise ValueError(f"cost_cap_usd out of range: {self.cost_cap_usd}")


class ProfileRegistry:
    """Process-wide registry of agent profiles.

    Thread-safe enough for our purposes: the registry is built at app
    startup and read on the hot path. Mutation after that (dynamic
    profile inserts) goes through register() which is not concurrent.
    """

    def __init__(self) -> None:
        self._by_name: dict[str, AgentProfile] = {}
        self._aliases: dict[str, str] = {}

    def register(
        self,
        profile: AgentProfile,
        *,
        aliases: tuple[str, ...] = (),
    ) -> None:
        if profile.name in self._by_name:
            raise ValueError(f"profile already registered: {profile.name}")
        if profile.name in self._aliases:
            raise ValueError(f"profile name collides with alias: {profile.name}")
        self._by_name[profile.name] = profile
        for a in aliases:
            if a == profile.name:
                continue
            if a in self._by_name or a in self._aliases:
                raise ValueError(f"alias collides: {a}")
            self._aliases[a] = profile.name

    def resolve(self, name: str) -> str:
        """Resolve an alias to its canonical name (or pass-through). Raises KeyError."""
        if name in self._by_name:
            return name
        if name in self._aliases:
            return self._aliases[name]
        raise KeyError(f"unknown profile: {name!r}")

    def get(self, name: str) -> AgentProfile:
        return self._by_name[self.resolve(name)]

    def names(self) -> list[str]:
        return sorted(self._by_name)

    def aliases(self) -> dict[str, str]:
        return dict(self._aliases)

    def __contains__(self, name: str) -> bool:
        try:
            self.resolve(name)
        except KeyError:
            return False
        return True

    def all_profiles(self) -> list[AgentProfile]:
        return [self._by_name[n] for n in self.names()]


# ---------------------------------------------------------------------
# Built-in employees — the hardcoded roster.
# ---------------------------------------------------------------------

# Shared tool sets. Naming them once keeps profile literals readable.
_READ_FILES = frozenset({"file.read"})
_WRITE_FILES = frozenset({"file.read", "file.write", "file.delete"})

_MEMORY_READ = frozenset({"memory.search"})
_MEMORY_WRITE = frozenset({"memory.search", "memory.add"})

_OBSIDIAN_READ = frozenset(
    {"obsidian.list", "obsidian.read", "obsidian.search", "obsidian.backlinks"}
)
_OBSIDIAN_WRITE = _OBSIDIAN_READ | frozenset({"obsidian.write", "obsidian.append"})

_GCAL = frozenset({"gcal.list_upcoming", "gcal.create_event"})
_GMAIL = frozenset({"gmail.draft", "gmail.send"})
_MAPS = frozenset({"maps.geocode", "maps.directions", "maps.places"})

# Forward-looking tool names. The actual ToolRegistry may not have these
# yet — they're surfaced as the registry grows. Profiles list intent;
# the runtime intersection prunes to what's available.
_DEBUG_TOOLS = frozenset({
    "events.recent", "events.by_trace",
    "audit.tail", "audit.by_trace",
    "runs.recent", "runs.get",
    "routing.stats",
})
_RUN_TESTS = frozenset({"shell.run_tests", "shell.run_lint"})
_ORCHESTRATION = frozenset({"agents.spawn", "agents.fan_out", "plans.submit"})


def built_in_profiles() -> list[tuple[AgentProfile, tuple[str, ...]]]:
    """The hardcoded roster + their aliases.

    Returned as (profile, aliases) tuples so register_built_ins() can
    wire them up without rebuilding the alias map by hand. The
    system_prompt strings live in vector.prompts to keep training
    edits in one place; we import them lazily to avoid a circular
    import at module load time.
    """
    from ..prompts import (
        DEBUGGER_AGENT_SYSTEM,
        DEVELOPER_AGENT_SYSTEM,
        ORCHESTRATOR_AGENT_SYSTEM,
        PROMPT_ENGINEER_AGENT_SYSTEM,
        RESEARCHER_AGENT_SYSTEM,
        SECURITY_AGENT_SYSTEM,
        SELF_HEALER_AGENT_SYSTEM,
        TESTER_AGENT_SYSTEM,
        WRITER_AGENT_SYSTEM,
    )

    return [
        (
            AgentProfile(
                name="developer",
                system_prompt=DEVELOPER_AGENT_SYSTEM,
                tools=_WRITE_FILES | _MEMORY_READ | _OBSIDIAN_READ,
                default_tier="sonnet",
                notes="File-editing, refactors, small implementations. "
                      "Renamed from 'code'.",
            ),
            ("code",),
        ),
        (
            AgentProfile(
                name="researcher",
                system_prompt=RESEARCHER_AGENT_SYSTEM,
                tools=(
                    _READ_FILES | _MEMORY_WRITE | _OBSIDIAN_WRITE
                    | _GCAL | frozenset({"gmail.draft"}) | _MAPS
                ),
                default_tier="sonnet",
                notes="Fact-finding with citations. Renamed from 'research'.",
            ),
            ("research",),
        ),
        (
            AgentProfile(
                name="writer",
                system_prompt=WRITER_AGENT_SYSTEM,
                tools=(
                    _WRITE_FILES | _MEMORY_WRITE | _OBSIDIAN_WRITE
                    | _GCAL | _GMAIL | _MAPS
                ),
                default_tier="haiku",
                notes="Drafts in Jason's voice. Owns the recipient memory.",
            ),
            (),
        ),
        (
            AgentProfile(
                name="tester",
                system_prompt=TESTER_AGENT_SYSTEM,
                tools=_WRITE_FILES | _MEMORY_READ | _OBSIDIAN_READ,
                default_tier="haiku",
                notes="pytest + vitest. Mirrors local conventions.",
            ),
            (),
        ),
        (
            AgentProfile(
                name="security",
                system_prompt=SECURITY_AGENT_SYSTEM,
                tools=_READ_FILES | _MEMORY_WRITE | _OBSIDIAN_READ,
                default_tier="opus",
                cost_cap_usd=2.0,
                notes="OWASP, secrets, ITAR. Read-only on files; writes "
                      "go to memory for prior-finding lookup.",
            ),
            (),
        ),
        (
            AgentProfile(
                name="debugger",
                system_prompt=DEBUGGER_AGENT_SYSTEM,
                tools=_READ_FILES | _MEMORY_READ | _OBSIDIAN_READ | _DEBUG_TOOLS,
                default_tier="sonnet",
                step_budget=20,  # bisecting often needs more steps
                notes="Root-cause analysis. Reads trace_id chains across "
                      "events, audit, runs. Never writes.",
            ),
            (),
        ),
        (
            AgentProfile(
                name="self_healer",
                system_prompt=SELF_HEALER_AGENT_SYSTEM,
                tools=_WRITE_FILES | _MEMORY_READ | _OBSIDIAN_READ | _RUN_TESTS,
                default_tier="sonnet",
                step_budget=20,
                cost_cap_usd=2.0,
                notes="Patch → test → re-patch loop. Used by the verifier "
                      "retry path when a developer agent fails its "
                      "success_criteria.",
            ),
            (),
        ),
        (
            AgentProfile(
                name="prompt_engineer",
                system_prompt=PROMPT_ENGINEER_AGENT_SYSTEM,
                tools=_READ_FILES | _MEMORY_WRITE | _OBSIDIAN_READ,
                default_tier="sonnet",
                notes="Produces AgentProfile JSON blobs when none of the "
                      "built-ins fit. Output is audited + stored before "
                      "any agent runs against it.",
            ),
            (),
        ),
        (
            AgentProfile(
                name="orchestrator",
                system_prompt=ORCHESTRATOR_AGENT_SYSTEM,
                tools=_MEMORY_READ | _OBSIDIAN_READ | _ORCHESTRATION,
                default_tier="opus",
                step_budget=24,
                cost_cap_usd=3.0,
                notes="Top-level planner. Decomposes goals into agent "
                      "calls. Does not edit files itself.",
            ),
            (),
        ),
    ]


def make_default_registry() -> ProfileRegistry:
    reg = ProfileRegistry()
    for profile, aliases in built_in_profiles():
        reg.register(profile, aliases=aliases)
    return reg


# ---------------------------------------------------------------------
# Process-wide singleton. Tests get a fresh registry via make_default_registry().
# ---------------------------------------------------------------------

_default_registry: ProfileRegistry | None = None


def default_registry() -> ProfileRegistry:
    """Return the lazily-built singleton registry. Idempotent."""
    global _default_registry
    if _default_registry is None:
        _default_registry = make_default_registry()
    return _default_registry


def reset_default_registry() -> None:
    """For tests: drop the singleton so the next call rebuilds it."""
    global _default_registry
    _default_registry = None
