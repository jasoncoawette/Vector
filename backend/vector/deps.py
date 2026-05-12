from __future__ import annotations

import sqlite3
from pathlib import Path

from .agents import AgentManager
from .agents.types import AgentSpec, RunResult
from .config import get_settings
from .store import connect

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


def get_agents() -> AgentManager:
    global _agents
    if _agents is None:
        s = get_settings()
        _agents = AgentManager(
            executor=_placeholder_executor,
            max_parallel=s.max_parallel_agents,
        )
    return _agents


def set_agents(mgr: AgentManager | None) -> None:
    global _agents
    _agents = mgr
