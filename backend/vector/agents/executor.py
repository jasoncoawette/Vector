from __future__ import annotations

from dataclasses import dataclass

from ..tools.errors import NeedsConfirm, ToolDenied, ToolError
from ..tools.registry import Registry
from ..voice.brain import Brain, BrainReply
from .types import AgentSpec, RunResult

SYSTEM_PROMPTS = {
    "code": (
        "You are a coding sub-agent for Vector. "
        "Work in small steps. Use tools for file IO. "
        "Stop and return when the requested change is complete."
    ),
    "research": (
        "You are a research sub-agent for Vector. "
        "Pull from the safe-list of sources. "
        "Cite each fact with the URL it came from."
    ),
    "writer": (
        "You are a writing sub-agent for Vector. "
        "Match Jason's voice: short sentences, no filler, action-first."
    ),
}

MAX_STEPS = 12


@dataclass
class ClaudeAgentExecutor:
    """Drives an AgentSpec through a brain + tool registry."""

    brain_factory: callable
    registry: Registry | None = None
    max_steps: int = MAX_STEPS

    async def __call__(self, spec: AgentSpec, prompt: str) -> RunResult:
        brain: Brain = self.brain_factory(spec.type)
        history: list[dict] = []
        total_cost = 0.0
        final_text = ""
        steps = 0
        last_call_sig: tuple | None = None
        repeats = 0

        while steps < self.max_steps:
            steps += 1
            reply: BrainReply = await brain.plan(prompt, history)
            total_cost += reply.cost_usd
            if reply.tool_call:
                sig = (reply.tool_call.get("name"), tuple(sorted((reply.tool_call.get("args") or {}).items())))
                if sig == last_call_sig:
                    repeats += 1
                else:
                    repeats = 1
                    last_call_sig = sig
                if repeats >= 5:
                    return RunResult(
                        output=final_text or "[loop aborted]",
                        cost_usd=total_cost,
                        meta={"aborted": "loop_detected", "steps": steps},
                    )
                tool_output: str
                if self.registry is None:
                    tool_output = "[no registry]"
                else:
                    try:
                        result = self.registry.call(
                            reply.tool_call["name"], reply.tool_call.get("args") or {}
                        )
                        tool_output = str(result)[:4000]
                    except NeedsConfirm as e:
                        tool_output = f"needs_confirm: {e}; token={e.token}"
                    except ToolDenied as e:
                        tool_output = f"denied: {e}"
                    except ToolError as e:
                        tool_output = f"tool_error: {e}"
                history.append({"role": "assistant", "tool_call": reply.tool_call})
                history.append({"role": "tool", "content": tool_output})
                continue
            final_text = reply.text or final_text
            if reply.final:
                break

        return RunResult(
            output=final_text,
            cost_usd=total_cost,
            meta={"steps": steps},
        )
