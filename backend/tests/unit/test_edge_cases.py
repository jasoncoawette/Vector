"""Edge-case tests surfaced by the post-Phase-9 code review.

Each test names the gap it covers in the docstring."""

from __future__ import annotations

import asyncio
import os
import unicodedata
from datetime import datetime

import pytest


# ---- 1. greeting boundary ------------------------------------------------


def test_greeting_at_exact_noon_is_afternoon():
    """`hour < 12` boundary: 12:00:00 must be afternoon, not morning."""
    from vector.app import _greeting_for

    assert _greeting_for(datetime(2026, 5, 12, 11, 59, 59)).startswith("Good morning")
    assert _greeting_for(datetime(2026, 5, 12, 12, 0, 0)).startswith("Good afternoon")


def test_greeting_at_exact_six_pm_is_evening():
    from vector.app import _greeting_for

    assert _greeting_for(datetime(2026, 5, 12, 17, 59, 59)).startswith("Good afternoon")
    assert _greeting_for(datetime(2026, 5, 12, 18, 0, 0)).startswith("Good evening")


# ---- 2. weekly bounds across a DST-equivalent week boundary -------------


def test_weekly_bounds_span_full_seven_days():
    """`_week_bounds` returns a 7-day range regardless of which weekday
    `now` falls on. (Naive datetime, so this is the contract; DST drift
    is a known footnote.)"""
    from vector.engine.weekly import _week_bounds

    for weekday in range(7):
        # Sunday-the-13th, Monday-the-14th, etc.
        now = datetime(2026, 5, 11 + weekday, 16, 0)
        start, end = _week_bounds(now)
        seconds = end - start
        # Allow a 1-hour DST cushion either way.
        assert 23 * 3600 <= seconds / 7 <= 25 * 3600
        assert 6 * 24 * 3600 < seconds <= 7 * 24 * 3600 + 3600


def test_weekly_bounds_start_is_monday_midnight():
    from vector.engine.weekly import _week_bounds

    # Tuesday 2026-05-12.
    now = datetime(2026, 5, 12, 14, 30)
    start, _end = _week_bounds(now)
    start_dt = datetime.fromtimestamp(start)
    assert start_dt.weekday() == 0  # Monday
    assert start_dt.hour == 0
    assert start_dt.minute == 0


# ---- 3. macOS NFD vs NFC filename normalization -------------------------


def test_unicode_normalization_does_not_break_scope_check(tmp_path):
    """Some filesystems normalize filenames (NFD on macOS, NFC on Linux).
    The guard should accept both forms as long as the resolved path is
    inside the read root."""
    from vector.tools.files import FileGuard

    read_root = tmp_path / "home"
    read_root.mkdir()
    guard = FileGuard(read_root=read_root, write_root=read_root / "ws")

    nfc = unicodedata.normalize("NFC", "café.txt")
    nfd = unicodedata.normalize("NFD", "café.txt")
    assert nfc != nfd

    target = guard.write_root / nfc
    guard.write(str(target), "hello")
    # Same logical file via either form: read may succeed (NFC), or fail
    # cleanly with a not-found denial (NFD on a filesystem that doesn't
    # normalize). Either is fine; what's NOT fine is a scope escape.
    for form in (nfc, nfd):
        path = guard.write_root / form
        try:
            out = guard.read(str(path))
            assert out["text"] == "hello"
        except Exception as e:  # noqa: BLE001
            assert "outside" not in str(e), f"normalization caused scope escape: {e}"


# ---- 4. symlink loop in _resolve ----------------------------------------


def test_symlink_loop_does_not_crash(tmp_path):
    """A symlink that points to itself shouldn't take down the guard."""
    from vector.tools.errors import ToolDenied
    from vector.tools.files import FileGuard

    read_root = tmp_path / "home"
    read_root.mkdir()
    guard = FileGuard(read_root=read_root, write_root=read_root / "ws")
    loop = read_root / "loop"
    os.symlink(loop, loop)
    # Either denied as out of scope, or denied as failed-to-resolve.
    with pytest.raises(ToolDenied):
        guard.read(str(loop))


# ---- 5. auto-security after a fallback-recovered code run ---------------


async def test_auto_security_fires_when_code_recovers_via_fallback():
    """Per the review: an agent that failed once and recovered via
    fallback ends in DONE and SHOULD trigger a security review. Verify
    that's the behavior."""
    from vector.agents import AgentManager, AgentSpec, RunResult
    from vector.agents.auto_security import register_auto_security
    from vector.hooks import HookRegistry

    seen_types: list[str] = []

    async def exec_(spec, prompt):
        seen_types.append(spec.type)
        if spec.type == "code" and prompt == "primary":
            raise RuntimeError("first attempt failed")
        return RunResult(output="ok", cost_usd=0.01)

    hooks = HookRegistry()
    mgr = AgentManager(executor=exec_, max_parallel=4, hooks=hooks)
    register_auto_security(mgr, hooks=hooks)
    code = await mgr.spawn(
        AgentSpec(
            type="code",
            prompt="primary",
            fallback_prompt="backup",
            files=frozenset({"/a.py"}),
        )
    )
    await mgr.wait(code.id)
    assert code.fallback_used is True
    assert code.status.value == "done"

    for _ in range(40):
        await asyncio.sleep(0.02)
        if any(r.spec.type == "security" for r in mgr.list_runs()):
            break
    sec_runs = [r for r in mgr.list_runs() if r.spec.type == "security"]
    assert len(sec_runs) == 1
    assert sec_runs[0].spec.files == frozenset({"/a.py"})


# ---- 6. refocus while the manager is paused -----------------------------


async def test_refocus_while_paused_queues_new_run():
    """Documented behavior: refocus kills the old run, spawns a new one;
    the new run waits in _acquire_slot until resume()."""
    from vector.agents import AgentManager, AgentSpec, RunResult, RunStatus

    started = asyncio.Event()

    async def exec_(spec, prompt):
        started.set()
        await asyncio.sleep(5)
        return RunResult(output="never")

    mgr = AgentManager(executor=exec_, max_parallel=2)
    original = await mgr.spawn(AgentSpec(type="code", prompt="v1"))
    await started.wait()
    await mgr.pause()

    new_run = await mgr.refocus(original.id, "v2")
    assert new_run is not None
    assert original.status == RunStatus.KILLED
    await asyncio.sleep(0.05)
    assert new_run.status == RunStatus.QUEUED


async def test_refocus_while_paused_resumes_correctly():
    """After resume(), the queued refocus run actually proceeds."""
    from vector.agents import AgentManager, AgentSpec, RunResult, RunStatus

    state = {"first_started": False}

    async def exec_(spec, prompt):
        if not state["first_started"]:
            state["first_started"] = True
            await asyncio.sleep(5)
            return RunResult(output="never")
        return RunResult(output=f"completed {prompt}")

    mgr = AgentManager(executor=exec_, max_parallel=2)
    original = await mgr.spawn(AgentSpec(type="code", prompt="v1"))
    for _ in range(20):
        await asyncio.sleep(0.01)
        if state["first_started"]:
            break
    await mgr.pause()
    new_run = await mgr.refocus(original.id, "v2")
    assert new_run is not None
    await mgr.resume()
    await mgr.wait(new_run.id, timeout=2)
    assert new_run.status == RunStatus.DONE
    assert "v2" in new_run.output


# ---- 7. HashEmbedder collisions are bounded -----------------------------


def test_hash_embedder_collisions_do_not_explode_norm():
    """Two completely different strings shouldn't normalize to the same
    vector, but their cosine similarity should also stay in [-1, 1]
    even with hash collisions."""
    from vector.memory import HashEmbedder
    from vector.memory.store import _cosine

    e = HashEmbedder()
    a = e.embed("ship the Stratus CLI today")
    b = e.embed("buy groceries on the way home")
    sim = _cosine(a, b)
    assert -1.001 <= sim <= 1.001
    # The embedding is unit-norm: dot with itself == 1.
    assert _cosine(a, a) == pytest.approx(1.0, abs=1e-6)


def test_hash_embedder_handles_repeated_tokens():
    """Repeated tokens shouldn't blow up the norm or produce NaN."""
    from vector.memory import HashEmbedder

    e = HashEmbedder()
    v = e.embed("aaa " * 1000)
    norm = sum(x * x for x in v) ** 0.5
    assert 0.99 < norm < 1.01


# ---- 8. memory store with a corrupted embedding blob --------------------


def test_search_with_truncated_embedding_returns_zero_score(tmp_path):
    """If a `memories.embedding` blob is corrupted to a partial length,
    _cosine returns 0 (since dims don't match) — the row is still
    returned, just ranked last."""
    from vector.memory import HashEmbedder, SqliteMemoryStore
    from vector.store import connect

    conn = connect(tmp_path / "v.db")
    try:
        store = SqliteMemoryStore(conn, HashEmbedder())
        good_id = store.add("note", "a clean memory")
        # Tamper: truncate the embedding to half its bytes.
        row = conn.execute(
            "SELECT embedding FROM memories WHERE id = ?", (good_id,)
        ).fetchone()
        half = row["embedding"][: len(row["embedding"]) // 2]
        bad_id = conn.execute(
            "INSERT INTO memories(kind, text, embedding, meta, recorded_at) "
            "VALUES(?, ?, ?, ?, ?)",
            ("note", "corrupted memory", half, "{}", 0.0),
        ).lastrowid

        hits = store.search("clean memory", k=5)
        ids = [h.id for h in hits]
        assert good_id in ids
        assert bad_id in ids
        # The corrupted row should score zero — below the good one.
        scores = {h.id: h.score for h in hits}
        assert scores[bad_id] == 0.0
        assert scores[good_id] > 0.0
    finally:
        conn.close()


# ---- 9. webhook signature edge inputs -----------------------------------


def test_webhook_whitespace_only_signature_rejected():
    from vector.webhooks.linear import verify_linear_signature

    with pytest.raises(ValueError):
        verify_linear_signature(b'{"x":1}', signature="   ", secret="s")


def test_webhook_empty_signature_rejected():
    from vector.webhooks.linear import verify_linear_signature

    with pytest.raises(ValueError):
        verify_linear_signature(b'{"x":1}', signature="", secret="s")


# ---- 10. file guard read of an empty file -------------------------------


def test_read_empty_file_returns_empty_text(tmp_path):
    """Empty file: no nulls in the first 4KB peek, size 0; should
    return text='' without erroring."""
    from vector.tools.files import FileGuard

    read_root = tmp_path / "home"
    read_root.mkdir()
    guard = FileGuard(read_root=read_root, write_root=read_root / "ws")
    target = guard.write_root / "empty.txt"
    target.write_text("")
    out = guard.read(str(target))
    assert out["text"] == ""
    assert out["binary"] is False
    assert out["size"] == 0
