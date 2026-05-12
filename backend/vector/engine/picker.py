from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass

from ..store import tasks as tasks_repo
from ..store.tasks import Task

DEFAULT_WEIGHTS: dict[str, float] = {
    "outcome": 1.0,
    "priority": 1.0,
    "stratus": 1.0,
    "calendar_today": 0.5,
    "boeing_penalty": -0.75,
}

TOP_N = 3


@dataclass
class Pick:
    task: Task
    score: float
    reason: str


def _features(task: Task, calendar_today_ids: set[str]) -> dict[str, float]:
    f: dict[str, float] = {}
    f["outcome"] = 1.0 if task.tag == "outcome" else 0.0
    f["priority"] = max(0.0, (5 - task.priority) / 4.0)
    f["stratus"] = 1.0 if task.mission == "stratus" else 0.0
    f["boeing_penalty"] = 1.0 if task.mission == "boeing" else 0.0
    f["calendar_today"] = (
        1.0 if task.external_id and task.external_id in calendar_today_ids else 0.0
    )
    return f


def load_weights(conn: sqlite3.Connection) -> dict[str, float]:
    rows = conn.execute("SELECT feature, weight FROM picker_weights").fetchall()
    weights = dict(DEFAULT_WEIGHTS)
    for r in rows:
        weights[r["feature"]] = r["weight"]
    return weights


def save_weights(conn: sqlite3.Connection, weights: dict[str, float]) -> None:
    for feature, weight in weights.items():
        conn.execute(
            """
            INSERT INTO picker_weights(feature, weight) VALUES(?, ?)
            ON CONFLICT(feature) DO UPDATE SET weight=excluded.weight
            """,
            (feature, weight),
        )


def _score(task: Task, weights: dict[str, float], cal_ids: set[str]) -> tuple[float, dict[str, float]]:
    feats = _features(task, cal_ids)
    total = sum(weights.get(k, 0.0) * v for k, v in feats.items())
    return total, feats


def _reason(feats: dict[str, float], task: Task) -> str:
    parts: list[str] = []
    if feats.get("outcome", 0) > 0:
        parts.append("outcome work")
    if feats.get("stratus", 0) > 0:
        parts.append("Stratus aligned")
    if feats.get("calendar_today", 0) > 0:
        parts.append("on today's calendar")
    if feats.get("priority", 0) >= 0.75:
        parts.append("high priority")
    if feats.get("boeing_penalty", 0) > 0:
        parts.append("Boeing — deferred")
    if not parts:
        parts.append("next in the queue")
    return f"{task.title}: {', '.join(parts)}"


def pick_top(
    conn: sqlite3.Connection,
    *,
    day: str,
    calendar_today_ids: set[str] | None = None,
    n: int = TOP_N,
) -> list[Pick]:
    weights = load_weights(conn)
    cal_ids = calendar_today_ids or set()
    scored: list[Pick] = []
    for t in tasks_repo.list_open(conn):
        score, feats = _score(t, weights, cal_ids)
        scored.append(Pick(task=t, score=score, reason=_reason(feats, t)))
    scored.sort(key=lambda p: (-p.score, p.task.id))
    return scored[:n]


def log_picks(conn: sqlite3.Connection, day: str, picks: list[Pick]) -> None:
    conn.execute("DELETE FROM picks WHERE day = ?", (day,))
    for rank, p in enumerate(picks, start=1):
        conn.execute(
            "INSERT INTO picks(day, rank, task_id, reason, score) VALUES(?, ?, ?, ?, ?)",
            (day, rank, p.task.id, p.reason, p.score),
        )


def record_override(
    conn: sqlite3.Connection,
    *,
    day: str,
    removed_task_id: int,
    added_task_id: int,
    learning_rate: float = 0.1,
    hooks: "object | None" = None,
) -> dict[str, float]:
    conn.execute(
        "INSERT INTO overrides(day, removed_task_id, added_task_id, created_at) VALUES(?, ?, ?, ?)",
        (day, removed_task_id, added_task_id, time.time()),
    )
    removed = tasks_repo.get(conn, removed_task_id)
    added = tasks_repo.get(conn, added_task_id)
    weights = load_weights(conn)
    if removed and added:
        removed_feats = _features(removed, set())
        added_feats = _features(added, set())
        for feature in set(removed_feats) | set(added_feats):
            delta = added_feats.get(feature, 0.0) - removed_feats.get(feature, 0.0)
            if delta:
                weights[feature] = weights.get(feature, 0.0) + learning_rate * delta
        save_weights(conn, weights)
    if hooks is not None:
        try:
            hooks.emit_nowait(
                "pick_override",
                {
                    "day": day,
                    "removed": removed_task_id,
                    "added": added_task_id,
                    "weights": weights,
                },
            )
        except Exception:  # noqa: BLE001
            pass
    return weights
