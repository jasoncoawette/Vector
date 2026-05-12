from __future__ import annotations

from dataclasses import dataclass

from ..prompts import SYSTEM_PROMPTS
from ..tools.errors import NeedsConfirm, ToolDenied, ToolError
from ..tools.registry import Registry
from ..voice.brain import Brain, BrainReply
from .types import AgentSpec, RunResult

MAX_STEPS = 12


@dataclass
class ClaudeAgentExecutor:
    """Drives an AgentSpec through a brain + tool registry."""

    brain_factory: callable
    registry: Registry | None = None
    registry_factory: callable | None = None
    max_steps: int = MAX_STEPS

    def _registry_for(self, agent_type: str) -> Registry | None:
        if self.registry_factory is not None:
            return self.registry_factory(agent_type)
        return self.registry

    async def __call__(self, spec: AgentSpec, prompt: str) -> RunResult:
        try:
            brain: Brain = self.brain_factory(spec.type, prompt=prompt)
        except TypeError:
            brain = self.brain_factory(spec.type)
        active_registry = self._registry_for(spec.type)
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
                if active_registry is None:
                    tool_output = "[no registry]"
                else:
                    try:
                        result = active_registry.call(
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
