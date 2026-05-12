from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from vector.agents import AgentManager, AgentSpec
from vector.agents.executor import ClaudeAgentExecutor
from vector.tools.builder import build_default_registry
from vector.tools.files import FileGuard
from vector.voice.brain import BrainReply, ClaudeBrain, FakeBrain, estimate_cost


@dataclass
class _Usage:
    input_tokens: int
    output_tokens: int


@dataclass
class _Block:
    type: str
    text: str = ""
    id: str = ""
    name: str = ""
    input: dict | None = None


@dataclass
class _Resp:
    content: list[_Block]
    usage: _Usage
    stop_reason: str = "end_turn"


class FakeClient:
    def __init__(self, responses: list[_Resp]) -> None:
        self._responses = list(responses)
        self.last_kwargs: dict[str, Any] | None = None

    async def create(self, **kwargs: Any) -> _Resp:
        self.last_kwargs = kwargs
        return self._responses.pop(0)


async def test_claude_brain_returns_text_and_cost():
    client = FakeClient(
        [_Resp(content=[_Block(type="text", text="hello")], usage=_Usage(100, 50))]
    )
    brain = ClaudeBrain(api_key="k", model="claude-sonnet-4-6", client=client)
    reply = await brain.plan("hi", [])
    assert reply.text == "hello"
    assert reply.final is True
    assert reply.cost_usd > 0


async def test_claude_brain_extracts_tool_call():
    client = FakeClient(
        [
            _Resp(
                content=[
                    _Block(
                        type="tool_use",
                        id="t1",
                        name="file.read",
                        input={"path": "/x.md"},
                    )
                ],
                usage=_Usage(50, 10),
                stop_reason="tool_use",
            )
        ]
    )
    brain = ClaudeBrain(
        api_key="k",
        model="claude-sonnet-4-6",
        client=client,
        tool_schemas=[{"name": "file.read"}],
    )
    reply = await brain.plan("read it", [])
    assert reply.tool_call is not None
    assert reply.tool_call["name"] == "file.read"
    assert reply.tool_call["args"] == {"path": "/x.md"}
    assert reply.final is False


async def test_brain_passes_system_when_provided():
    client = FakeClient(
        [_Resp(content=[_Block(type="text", text="ok")], usage=_Usage(1, 1))]
    )
    brain = ClaudeBrain(
        api_key="k",
        model="claude-sonnet-4-6",
        client=client,
        system="you are vector",
    )
    await brain.plan("hi", [])
    assert client.last_kwargs["system"] == "you are vector"


def test_estimate_cost_known_model():
    c = estimate_cost("claude-sonnet-4-6", 1_000_000, 1_000_000)
    assert c == pytest.approx(3.0 + 15.0)


def test_estimate_cost_unknown_model_uses_defaults():
    assert estimate_cost("unknown", 1_000_000, 0) == pytest.approx(3.0)


async def test_executor_runs_to_final_text():
    def factory(_type: str):
        return FakeBrain([BrainReply(text="all done", final=True, cost_usd=0.05)])

    ex = ClaudeAgentExecutor(brain_factory=factory)
    out = await ex(AgentSpec(type="research", prompt="go"), "go")
    assert out.output == "all done"
    assert out.cost_usd == pytest.approx(0.05)


async def test_executor_dispatches_tool_call(tmp_path):
    read_root = tmp_path / "home"
    read_root.mkdir()
    guard = FileGuard(read_root=read_root, write_root=read_root / "ws")
    target = guard.write_root / "x.txt"
    target.write_text("payload-from-disk")
    reg = build_default_registry(guard)

    def factory(_type: str):
        return FakeBrain(
            [
                BrainReply(
                    tool_call={"name": "file.read", "args": {"path": str(target)}},
                    final=False,
                    cost_usd=0.01,
                ),
                BrainReply(text="finished after read", final=True, cost_usd=0.01),
            ]
        )

    ex = ClaudeAgentExecutor(brain_factory=factory, registry=reg)
    out = await ex(AgentSpec(type="code", prompt="read it"), "read it")
    assert out.output == "finished after read"
    assert out.meta["steps"] == 2


async def test_executor_loop_guard():
    same_call = {"name": "file.read", "args": {"path": "/a"}}

    def factory(_type: str):
        return FakeBrain(
            [BrainReply(tool_call=same_call, final=False, cost_usd=0.0) for _ in range(20)]
        )

    ex = ClaudeAgentExecutor(brain_factory=factory, registry=None)
    out = await ex(AgentSpec(type="research", prompt="loop"), "loop")
    assert out.meta.get("aborted") == "loop_detected"


async def test_executor_via_agent_manager(tmp_path):
    read_root = tmp_path / "home"
    read_root.mkdir()
    guard = FileGuard(read_root=read_root, write_root=read_root / "ws")
    reg = build_default_registry(guard)

    def factory(_type: str):
        return FakeBrain([BrainReply(text="ok", final=True, cost_usd=0.02)])

    ex = ClaudeAgentExecutor(brain_factory=factory, registry=reg)
    mgr = AgentManager(executor=ex, max_parallel=2)
    run = await mgr.spawn(AgentSpec(type="writer", prompt="draft"))
    await mgr.wait(run.id)
    assert run.status.value == "done"
    assert run.output == "ok"
