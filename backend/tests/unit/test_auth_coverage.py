from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from vector.agents import AgentManager, RunResult
from vector.app import app, set_registry
from vector.config import get_settings
from vector.deps import set_agents, set_db


@pytest.fixture()
def secured(tmp_path: Path):
    from vector.store import connect
    from vector.tools.builder import build_default_registry
    from vector.tools.files import FileGuard

    conn = connect(tmp_path / "v.db")
    set_db(conn)

    read_root = tmp_path / "home"
    read_root.mkdir()
    guard = FileGuard(read_root=read_root, write_root=read_root / "ws")
    set_registry(build_default_registry(guard))

    async def exec_fast(spec, prompt):
        return RunResult(output="ok", cost_usd=0.01)

    set_agents(AgentManager(executor=exec_fast, max_parallel=3))

    s = get_settings()
    original = s.backend_bearer
    s.backend_bearer = "test-token"
    try:
        yield TestClient(app), guard, "test-token"
    finally:
        s.backend_bearer = original
        set_agents(None)
        set_registry(None)
        set_db(None)
        conn.close()


def test_tools_call_without_bearer_is_401(secured):
    c, guard, _ = secured
    r = c.post(
        "/tools/call",
        json={"name": "file.read", "args": {"path": str(guard.write_root / "x")}},
    )
    assert r.status_code == 401


def test_tools_call_with_bearer_passes_auth(secured):
    c, guard, token = secured
    (guard.write_root / "x.txt").write_text("hello")
    r = c.post(
        "/tools/call",
        json={"name": "file.read", "args": {"path": str(guard.write_root / "x.txt")}},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200


def test_metric_post_requires_bearer(secured):
    c, _, _ = secured
    r = c.post("/metrics", json={"section": "stratus", "name": "x", "value": 1})
    assert r.status_code == 401


def test_tasks_post_requires_bearer(secured):
    c, _, _ = secured
    r = c.post("/tasks", json={"title": "x"})
    assert r.status_code == 401


def test_daily_review_requires_bearer(secured):
    c, _, _ = secured
    r = c.post("/daily/review", json={"day": "2026-05-12", "shipped_ids": []})
    assert r.status_code == 401


def test_ws_without_bearer_is_closed(secured):
    c, _, _ = secured
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect):
        with c.websocket_connect("/voice/stream") as ws:
            ws.receive()


def test_ws_with_correct_bearer_accepts(secured):
    c, _, token = secured
    # Use a session factory so the WS produces a deterministic IDLE event.
    from vector.deps import set_session_factory
    from vector.voice.brain import BrainReply, FakeBrain
    from vector.voice.session import VoiceSession
    from vector.voice.stt import FakeSTT

    class _NoTTS:
        async def stream(self, text: str):
            if False:
                yield b""
            return

    def factory():
        return VoiceSession(
            stt=FakeSTT(transcripts=[""]),
            brain=FakeBrain([BrainReply(text="x", final=True)]),
            tts=_NoTTS(),
        )

    set_session_factory(factory)
    try:
        with c.websocket_connect(f"/voice/stream?token={token}") as ws:
            ws.send_bytes(b"\x00")
            ws.send_text('{"type":"end"}')
            saw_state = False
            for _ in range(10):
                msg = ws.receive()
                if "text" in msg and msg["text"]:
                    saw_state = True
                    break
            assert saw_state
    finally:
        set_session_factory(None)


def test_ws_wrong_token_is_closed(secured):
    c, _, _ = secured
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect):
        with c.websocket_connect("/voice/stream?token=wrong") as ws:
            ws.receive()
