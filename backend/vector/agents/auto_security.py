from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ..hooks import HookRegistry, get_hooks
from .types import AgentSpec

if TYPE_CHECKING:
    from .manager import AgentManager

logger = logging.getLogger("vector.auto_security")

# Cost cap for auto-spawned security reviews. Lower than the default
# $1 spec cap because security reviews should be cheap audits, not
# deep architectural rewrites.
DEFAULT_REVIEW_COST_CAP_USD = 0.25
DEFAULT_REVIEW_TIMEOUT_S = 300


def _build_security_prompt(code_run: dict) -> str:
    files = code_run.get("files") or []
    file_clause = ""
    if files:
        file_clause = "\nFiles changed:\n" + "\n".join(f"- {p}" for p in files)
    original = code_run.get("prompt", "")
    return (
        "A code sub-agent just completed this task:\n"
        f"  {original}\n"
        f"{file_clause}\n\n"
        "Audit the resulting diff for OWASP top-10 issues, secret leakage, "
        "scope-escape, and ITAR boundary violations. Return findings as a "
        "list with severity (low/med/high) and a one-line fix for each."
    )


def register_auto_security(
    mgr: "AgentManager",
    *,
    hooks: HookRegistry | None = None,
    cost_cap_usd: float = DEFAULT_REVIEW_COST_CAP_USD,
    timeout_s: int = DEFAULT_REVIEW_TIMEOUT_S,
):
    """Register a listener that fans out a security agent after every
    successful `code` run. Returns the unsubscribe handle so callers can
    detach in tests."""
    reg = hooks or get_hooks()

    async def on_agent_complete(payload: dict) -> None:
        run = payload.get("run") or {}
        if run.get("type") != "code":
            return
        if run.get("status") != "done":
            return
        spec = AgentSpec(
            type="security",
            prompt=_build_security_prompt(run),
            files=frozenset(run.get("files") or ()),
            cost_cap_usd=cost_cap_usd,
            timeout_s=timeout_s,
        )
        try:
            new_run = await mgr.spawn(spec)
            logger.info(
                "auto-security spawned %s for code run %s", new_run.id, run.get("id")
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("auto-security spawn failed: %s", e)

    return reg.on("agent_complete", on_agent_complete)
