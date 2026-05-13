"""Daily-brief scheduler.

Background asyncio task started by app startup. Ticks once per minute,
reads the `daily_brief` preference, and when the configured local time
arrives it renders today's brief and drops it into the voice inbox.

Why in-process + asyncio instead of cron/launchd:
  • A single failure surface — the same Python process that builds the
    brief also speaks it, so token spend, audit, and tracing flow into
    one trace_id.
  • Restarts replay safely: already_delivered_today() guards against
    double-firing inside the same local day.
  • Tests can call tick() directly with a frozen `now`.

What we DON'T do here:
  • Drive TTS. The scheduler is the producer; the desktop client (or a
    follow-up WebSocket pusher) consumes from /voice/inbox.
  • Reach into Google Calendar. The picker already handles calendar
    boosts; we just call render_morning_brief().
"""
from __future__ import annotations

import asyncio
import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from .engine import brief as brief_mod
from .engine import picker
from .store import inbox as inbox_store
from .store import preferences as prefs_store

logger = logging.getLogger("vector.scheduler")

PREF_DAILY_BRIEF = "daily_brief"

# Brief defaults if a caller sets the pref without all fields filled in.
# Time is HH:MM in the user's local timezone.
DEFAULT_BRIEF_PREFS: dict[str, Any] = {
    "enabled": True,
    "time": "08:00",
    "tz_offset_hours": -7,  # America/Los_Angeles (DST handled below)
    "user": "Jason",
    "channel": "voice",
}


@dataclass(frozen=True)
class TickResult:
    """One scheduler tick outcome. Mirrors what gets written to
    scheduler_log so tests + the /scheduler/log endpoint stay consistent."""
    key: str
    outcome: str
    detail: str | None = None


def _local_now(offset_hours: float) -> datetime:
    """Wall-clock time at the configured UTC offset.

    We deliberately use a fixed offset rather than a tz database so the
    scheduler stays dependency-free. The user updates the offset
    twice a year for DST, or sets a true timezone library later.
    """
    return datetime.now(timezone.utc) + timedelta(hours=offset_hours)


def _parse_hhmm(value: str) -> tuple[int, int]:
    try:
        h, m = value.split(":", 1)
        hi, mi = int(h), int(m)
    except (ValueError, AttributeError) as exc:
        raise ValueError(f"bad HH:MM in preference time: {value!r}") from exc
    if not (0 <= hi <= 23 and 0 <= mi <= 59):
        raise ValueError(f"out-of-range HH:MM: {value!r}")
    return hi, mi


def _render_brief(conn: sqlite3.Connection, *, day_iso: str, user: str) -> str:
    """Produce the spoken text for the daily brief. Same path the
    /daily/brief HTTP endpoint uses, so the scheduler and a manual
    invocation stay in lockstep."""
    picks = picker.pick_top(conn, day=day_iso)
    return brief_mod.render_morning_brief(picks, now=datetime.now(), user=user)


def tick(
    conn: sqlite3.Connection,
    *,
    now: datetime | None = None,
) -> TickResult:
    """Run one scheduler decision.

    Exposed for tests + the manual /scheduler/tick endpoint. Returns the
    decision (also persisted to scheduler_log).
    """
    pref = prefs_store.get(conn, PREF_DAILY_BRIEF)
    if pref is None:
        result = TickResult(key=PREF_DAILY_BRIEF, outcome="skipped:disabled",
                            detail="no preference set")
        inbox_store.log_scheduler_tick(conn, key=result.key, outcome=result.outcome,
                                       detail=result.detail)
        return result

    config = {**DEFAULT_BRIEF_PREFS, **(pref.value or {})}
    if not config.get("enabled", True):
        result = TickResult(key=PREF_DAILY_BRIEF, outcome="skipped:disabled",
                            detail="enabled=false")
        inbox_store.log_scheduler_tick(conn, key=result.key, outcome=result.outcome,
                                       detail=result.detail)
        return result

    try:
        target_h, target_m = _parse_hhmm(config["time"])
    except ValueError as exc:
        result = TickResult(key=PREF_DAILY_BRIEF, outcome=f"error:bad_time",
                            detail=str(exc))
        inbox_store.log_scheduler_tick(conn, key=result.key, outcome=result.outcome,
                                       detail=result.detail)
        return result

    offset = float(config.get("tz_offset_hours", -7))
    local = now if now is not None else _local_now(offset)
    day_iso = local.date().isoformat()

    # Fire if we're at or past the target minute. The "at or past" lets a
    # process started at 08:05 still deliver the 08:00 brief that day —
    # but only once, because the next branch checks the inbox.
    if (local.hour, local.minute) < (target_h, target_m):
        result = TickResult(key=PREF_DAILY_BRIEF, outcome="skipped:not_due",
                            detail=f"local={local.hour:02d}:{local.minute:02d} "
                                   f"target={target_h:02d}:{target_m:02d}")
        inbox_store.log_scheduler_tick(conn, key=result.key, outcome=result.outcome,
                                       detail=result.detail)
        return result

    if inbox_store.already_delivered_today(conn, kind=PREF_DAILY_BRIEF,
                                           day_iso=day_iso):
        result = TickResult(key=PREF_DAILY_BRIEF,
                            outcome="skipped:already_delivered",
                            detail=f"day={day_iso}")
        inbox_store.log_scheduler_tick(conn, key=result.key, outcome=result.outcome,
                                       detail=result.detail)
        return result

    # Render + enqueue. If picker errors we record it as a tick error but
    # don't crash the scheduler loop — tomorrow's tick will retry.
    try:
        text = _render_brief(conn, day_iso=day_iso, user=str(config.get("user", "Jason")))
    except Exception as exc:  # noqa: BLE001 — surface to log, keep loop alive
        logger.exception("daily-brief render failed")
        result = TickResult(key=PREF_DAILY_BRIEF, outcome="error:render",
                            detail=f"{type(exc).__name__}: {exc}")
        inbox_store.log_scheduler_tick(conn, key=result.key, outcome=result.outcome,
                                       detail=result.detail)
        return result

    inbox_id = inbox_store.enqueue(
        conn,
        kind=PREF_DAILY_BRIEF,
        text=text,
        meta={"day_iso": day_iso, "channel": config.get("channel", "voice")},
    )
    result = TickResult(key=PREF_DAILY_BRIEF, outcome="fired",
                        detail=f"inbox_id={inbox_id} day={day_iso}")
    inbox_store.log_scheduler_tick(conn, key=result.key, outcome=result.outcome,
                                   detail=result.detail)
    return result


async def run_loop(
    db_factory: Callable[[], sqlite3.Connection],
    *,
    interval_s: float = 60.0,
    stop_event: asyncio.Event | None = None,
) -> None:
    """Run scheduler.tick() in a loop until stop_event is set.

    `db_factory` returns the live connection each tick so we never hold
    a stale handle across reconnects. Sleeps `interval_s` (default 60s)
    between ticks. Cancellable: await tasks .cancel() to stop.
    """
    stop = stop_event or asyncio.Event()
    while not stop.is_set():
        try:
            conn = db_factory()
            tick(conn)
        except Exception:  # noqa: BLE001
            logger.exception("scheduler tick crashed; continuing")
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval_s)
        except asyncio.TimeoutError:
            continue
