from __future__ import annotations

import sqlite3
from pathlib import Path

from .agents import AgentManager
from .agents.executor import SYSTEM_PROMPTS, ClaudeAgentExecutor
from .agents.types import AgentSpec, RunResult
from .config import get_settings
from .store import connect
from .voice.brain import Brain, ClaudeBrain

_conn: sqlite3.Connection | None = None
_agents: AgentManager | None = None


def get_db() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        s = get_settings()
        path = Path(s.workspace) / "vector.db"
        _conn = connect(path)
    return _conn


def set_db(conn: sqlite3.Connection | None) -> None:
    global _conn
    _conn = conn


async def _placeholder_executor(spec: AgentSpec, prompt: str) -> RunResult:
    return RunResult(
        output=f"[placeholder {spec.type}] {prompt[:200]}",
        cost_usd=0.0,
        meta={"executor": "placeholder"},
    )


def _build_anthropic_client(api_key: str):
    try:
        import anthropic
    except ImportError:
        return None
    return anthropic.AsyncAnthropic(api_key=api_key).messages


def _build_real_executor() -> ClaudeAgentExecutor | None:
    s = get_settings()
    if not s.anthropic_api_key:
        return None
    client = _build_anthropic_client(s.anthropic_api_key)
    if client is None:
        return None

    def factory(agent_type: str) -> Brain:
        model = s.brain_model_hot if agent_type != "code" else s.brain_model_hard
        return ClaudeBrain(
            api_key=s.anthropic_api_key,
            model=model,
            client=client,
            system=SYSTEM_PROMPTS.get(agent_type, ""),
        )

    return ClaudeAgentExecutor(brain_factory=factory, registry=None)


def get_agents() -> AgentManager:
    global _agents
    if _agents is None:
        s = get_settings()
        executor = _build_real_executor() or _placeholder_executor
        _agents = AgentManager(executor=executor, max_parallel=s.max_parallel_agents)
    return _agents


def set_agents(mgr: AgentManager | None) -> None:
    global _agents
    _agents = mgr
