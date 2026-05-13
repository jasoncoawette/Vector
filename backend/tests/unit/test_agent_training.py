"""Contract tests for the agent training prompts + tool-schema wiring.

These pin two invariants the sub-agents depend on:
  1. Every agent type's system prompt teaches the agent its tools,
     workflow, and limits — not just an identity line.
  2. Registries can render themselves as Anthropic tool schemas the
     brain can advertise in its `tools=` argument, so agents can
     actually call the tools they're told about.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from vector.prompts import (
    CODE_AGENT_SYSTEM,
    RESEARCH_AGENT_SYSTEM,
    SECURITY_AGENT_SYSTEM,
    SYSTEM_PROMPTS,
    TESTER_AGENT_SYSTEM,
    VERIFIER_SYSTEM,
    VOICE_BRAIN_SYSTEM,
    WRITER_AGENT_SYSTEM,
    compose,
)
from vector.tools.registry import Registry, Tool


# ---------------------------------------------------------------------
# 1. SYSTEM_PROMPTS contract
# ---------------------------------------------------------------------


def test_system_prompts_cover_every_agent_type():
    assert set(SYSTEM_PROMPTS.keys()) == {
        "code", "research", "writer", "tester", "security",
    }


def test_every_agent_prompt_teaches_its_tools_section():
    """Every per-type prompt names the tools it can call."""
    for agent_type, prompt in SYSTEM_PROMPTS.items():
        assert "Tools available to you:" in prompt, (
            f"{agent_type} prompt is missing a tool catalog"
        )


def test_every_agent_prompt_teaches_workflow_section():
    for agent_type, prompt in SYSTEM_PROMPTS.items():
        assert "Workflow for every run:" in prompt, (
            f"{agent_type} prompt is missing a workflow"
        )


def test_every_agent_prompt_teaches_where_to_find_section():
    for agent_type, prompt in SYSTEM_PROMPTS.items():
        assert "Where to find things:" in prompt, (
            f"{agent_type} prompt is missing 'where to find'"
        )


def test_every_agent_prompt_has_a_worked_example():
    """A worked <example>...</example> block keeps agents grounded."""
    for agent_type, prompt in SYSTEM_PROMPTS.items():
        assert "<example>" in prompt and "</example>" in prompt, (
            f"{agent_type} prompt is missing a worked example"
        )


def test_every_agent_prompt_teaches_step_budget():
    """All agents must know their tool-call ceiling."""
    for agent_type, prompt in SYSTEM_PROMPTS.items():
        assert "12 tool calls" in prompt, (
            f"{agent_type} prompt is missing the step-budget rule"
        )


def test_every_agent_prompt_teaches_tool_discovery_rule():
    """Agents must know not to fabricate tool names."""
    for agent_type, prompt in SYSTEM_PROMPTS.items():
        assert "tools are advertised" in prompt, (
            f"{agent_type} prompt is missing TOOL_DISCOVERY_RULE"
        )


def test_code_agent_prompt_mentions_file_tools_specifically():
    assert "file.read" in CODE_AGENT_SYSTEM
    assert "file.write" in CODE_AGENT_SYSTEM


def test_research_agent_prompt_mentions_memory_and_obsidian():
    assert "memory.search" in RESEARCH_AGENT_SYSTEM
    assert "obsidian.search" in RESEARCH_AGENT_SYSTEM


def test_writer_agent_prompt_mentions_jasons_voice():
    assert "Jason's voice" in WRITER_AGENT_SYSTEM
    assert "Stratus" in WRITER_AGENT_SYSTEM  # vocabulary clause


def test_tester_agent_prompt_mentions_pytest_and_vitest():
    assert "pytest" in TESTER_AGENT_SYSTEM
    assert "vitest" in TESTER_AGENT_SYSTEM


def test_security_agent_prompt_mentions_owasp_and_itar():
    assert "OWASP" in SECURITY_AGENT_SYSTEM
    assert "ITAR" in SECURITY_AGENT_SYSTEM


def test_verifier_prompt_demands_json():
    assert '{"success"' in VERIFIER_SYSTEM


def test_voice_brain_prompt_present_and_terse():
    # Voice brain should be much shorter than the sub-agent training prompts.
    assert len(VOICE_BRAIN_SYSTEM) > 200
    assert len(VOICE_BRAIN_SYSTEM) < len(CODE_AGENT_SYSTEM)


# ---------------------------------------------------------------------
# 2. compose() helper
# ---------------------------------------------------------------------


def test_compose_joins_with_blank_lines_and_drops_empties():
    out = compose("a", "", "  ", "b")
    assert out == "a\n\nb"


def test_compose_strips_each_clause():
    out = compose("  a  ", "\nb\n")
    assert out == "a\n\nb"


# ---------------------------------------------------------------------
# 3. Registry.to_anthropic_schemas() — tool advertising
# ---------------------------------------------------------------------


class _PingArgs(BaseModel):
    target: str = Field(min_length=1, description="hostname to ping")
    count: int = Field(default=3, ge=1, le=10)


class _EchoArgs(BaseModel):
    text: str


def _ping_handler(a: _PingArgs) -> str:
    return f"pong from {a.target} x{a.count}"


def _echo_handler(a: _EchoArgs) -> str:
    return a.text


def test_to_anthropic_schemas_renders_one_entry_per_tool():
    reg = Registry()
    reg.register(Tool(name="ping", schema=_PingArgs, handler=_ping_handler,
                      description="ping a host"))
    reg.register(Tool(name="echo", schema=_EchoArgs, handler=_echo_handler,
                      description="echo back"))
    schemas = reg.to_anthropic_schemas()
    assert len(schemas) == 2
    by_name = {s["name"]: s for s in schemas}
    assert {"ping", "echo"} == set(by_name.keys())


def test_to_anthropic_schemas_has_required_anthropic_fields():
    reg = Registry()
    reg.register(Tool(name="ping", schema=_PingArgs, handler=_ping_handler,
                      description="ping a host"))
    s = reg.to_anthropic_schemas()[0]
    assert s["name"] == "ping"
    assert s["description"] == "ping a host"
    assert "input_schema" in s
    assert s["input_schema"]["type"] == "object"
    assert "target" in s["input_schema"]["properties"]


def test_to_anthropic_schemas_omits_top_level_title():
    """Anthropic's API rejects a stray top-level `title` in input_schema."""
    reg = Registry()
    reg.register(Tool(name="ping", schema=_PingArgs, handler=_ping_handler))
    s = reg.to_anthropic_schemas()[0]
    assert "title" not in s["input_schema"]


def test_to_anthropic_schemas_preserves_field_defaults():
    reg = Registry()
    reg.register(Tool(name="ping", schema=_PingArgs, handler=_ping_handler))
    schema = reg.to_anthropic_schemas()[0]["input_schema"]
    assert schema["properties"]["count"]["default"] == 3


def test_to_anthropic_schemas_marks_required_fields():
    reg = Registry()
    reg.register(Tool(name="ping", schema=_PingArgs, handler=_ping_handler))
    schema = reg.to_anthropic_schemas()[0]["input_schema"]
    assert schema["required"] == ["target"]


def test_to_anthropic_schemas_empty_registry_returns_empty_list():
    assert Registry().to_anthropic_schemas() == []


def test_registry_names_lists_registered_tools():
    reg = Registry()
    reg.register(Tool(name="ping", schema=_PingArgs, handler=_ping_handler))
    reg.register(Tool(name="echo", schema=_EchoArgs, handler=_echo_handler))
    assert set(reg.names()) == {"ping", "echo"}


# ---------------------------------------------------------------------
# 4. Default registry from build_registry_for renders schemas cleanly.
# ---------------------------------------------------------------------


def test_default_registry_yields_valid_anthropic_schemas(tmp_path):
    from vector.tools.builder import build_registry_for
    from vector.tools.files import FileGuard

    work = tmp_path / "work"
    work.mkdir(exist_ok=True)
    guard = FileGuard(read_root=tmp_path, write_root=work)
    reg = build_registry_for("code", guard=guard)
    schemas = reg.to_anthropic_schemas()
    assert len(schemas) >= 3  # file.read / write / delete
    for s in schemas:
        assert isinstance(s["name"], str) and s["name"]
        assert isinstance(s["description"], str)
        assert s["input_schema"]["type"] == "object"
