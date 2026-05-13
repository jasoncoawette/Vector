"""Tests for the sandboxed shell-execution tools (RES-40).

These cover the first subprocess-spawning tools in the codebase, so
every guardrail is pinned by a test:

  * path scope (no `..`, no absolute escape)
  * argv only (shell=False)
  * minimal env (no VECTOR_* secrets)
  * hard timeout (TimeoutExpired → ShellTimeout)
  * output capping (last MAX_OUTPUT_BYTES)
  * FORBIDDEN_DYNAMIC_TOOLS membership
  * self_healer registry includes both tools
  * audit_blob rejects them in a dynamic profile
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from vector.agents.profile_store import (
    FORBIDDEN_DYNAMIC_TOOLS,
    ProfileAuditError,
    audit_blob,
)
from vector.tools.builder import build_registry_for
from vector.tools.files import FileGuard
from vector.tools.shell import (
    MAX_OUTPUT_BYTES,
    ShellRunner,
    ShellScopeError,
    ShellTimeout,
)


# ---------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    """A tmp-path repo root with a trivial passing pytest file."""
    test_file = tmp_path / "test_passes.py"
    test_file.write_text("def test_passes():\n    assert True\n")
    return tmp_path


@pytest.fixture()
def runner(repo: Path) -> ShellRunner:
    return ShellRunner(repo_root=repo, timeout_s=30)


# ---------------------------------------------------------------------
# 1. Happy path: run pytest in a tmp repo
# ---------------------------------------------------------------------


def test_run_tests_in_repo_root_path_ok(runner: ShellRunner) -> None:
    result = runner.run_tests(path="test_passes.py", framework="pytest")
    assert result.exit_code == 0, (
        f"pytest failed: stdout={result.stdout_tail!r} "
        f"stderr={result.stderr_tail!r}"
    )
    # pytest -q prints "1 passed in 0.01s" — match either tail.
    combined = result.stdout_tail + result.stderr_tail
    assert "passed" in combined
    # The summary parser should pick up the count.
    assert result.passed == 1
    assert result.failed in (None, 0)


# ---------------------------------------------------------------------
# 2. Scope checks
# ---------------------------------------------------------------------


def test_run_tests_rejects_path_escape(runner: ShellRunner) -> None:
    with pytest.raises(ShellScopeError):
        runner.run_tests(path="../etc/passwd", framework="pytest")


def test_run_tests_rejects_absolute_path_outside_root(runner: ShellRunner) -> None:
    with pytest.raises(ShellScopeError):
        runner.run_tests(path="/etc/passwd", framework="pytest")


def test_run_lint_rejects_path_escape(runner: ShellRunner) -> None:
    with pytest.raises(ShellScopeError):
        runner.run_lint(path="../etc/passwd", tool="ruff")


# ---------------------------------------------------------------------
# 3. Timeout
# ---------------------------------------------------------------------


def test_run_tests_enforces_timeout(
    runner: ShellRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_run(argv, **kwargs):
        # Simulate the kernel-side timeout that subprocess.run raises.
        raise subprocess.TimeoutExpired(cmd=argv, timeout=kwargs.get("timeout", 1))

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(ShellTimeout):
        runner.run_tests(path="test_passes.py", framework="pytest")


# ---------------------------------------------------------------------
# 4. Output capping
# ---------------------------------------------------------------------


def test_run_tests_caps_output_size(
    runner: ShellRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    big = b"x" * (MAX_OUTPUT_BYTES * 4)

    class _Completed:
        returncode = 0
        stdout = big
        stderr = big

    def fake_run(argv, **kwargs):
        return _Completed()

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = runner.run_tests(path="test_passes.py", framework="pytest")
    assert len(result.stdout_tail.encode("utf-8")) <= MAX_OUTPUT_BYTES
    assert len(result.stderr_tail.encode("utf-8")) <= MAX_OUTPUT_BYTES


# ---------------------------------------------------------------------
# 5. Argv contract
# ---------------------------------------------------------------------


def test_argv_uses_shell_false(
    runner: ShellRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict = {}

    class _Completed:
        returncode = 0
        stdout = b""
        stderr = b""

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        captured["kwargs"] = kwargs
        return _Completed()

    monkeypatch.setattr(subprocess, "run", fake_run)
    runner.run_tests(path="test_passes.py", framework="pytest")

    assert captured["kwargs"].get("shell") is False
    assert isinstance(captured["argv"], list)
    assert all(isinstance(a, str) for a in captured["argv"])
    # No string command line ever — that's the whole point.
    assert not isinstance(captured["argv"], str)


# ---------------------------------------------------------------------
# 6. Env minimization
# ---------------------------------------------------------------------


def test_minimal_env_no_user_secrets(
    runner: ShellRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Plant secrets that MUST NOT leak into the child env.
    monkeypatch.setenv("VECTOR_ANTHROPIC_API_KEY", "sk-do-not-leak")
    monkeypatch.setenv("VECTOR_LINEAR_API_KEY", "lin-secret")
    monkeypatch.setenv("VECTOR_OAUTH_TOKEN_KEY", "oauth-secret")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "aws-secret")

    captured: dict = {}

    class _Completed:
        returncode = 0
        stdout = b""
        stderr = b""

    def fake_run(argv, **kwargs):
        captured["env"] = kwargs.get("env")
        return _Completed()

    monkeypatch.setattr(subprocess, "run", fake_run)
    runner.run_tests(path="test_passes.py", framework="pytest")

    env = captured["env"]
    assert env is not None, "env must be explicitly set, not inherited"
    assert "VECTOR_ANTHROPIC_API_KEY" not in env
    assert "VECTOR_LINEAR_API_KEY" not in env
    assert "VECTOR_OAUTH_TOKEN_KEY" not in env
    assert "AWS_SECRET_ACCESS_KEY" not in env
    # PATH should be forwarded so /usr/bin/python is findable.
    assert "PATH" in env


# ---------------------------------------------------------------------
# 7. FORBIDDEN_DYNAMIC_TOOLS membership
# ---------------------------------------------------------------------


def test_shell_run_tests_in_FORBIDDEN_DYNAMIC_TOOLS() -> None:
    assert "shell.run_tests" in FORBIDDEN_DYNAMIC_TOOLS
    assert "shell.run_lint" in FORBIDDEN_DYNAMIC_TOOLS


# ---------------------------------------------------------------------
# 8. self_healer registry actually exposes the tools
# ---------------------------------------------------------------------


def test_self_healer_registry_includes_shell_tools(
    tmp_path: Path, repo: Path
) -> None:
    read_root = tmp_path / "home"
    read_root.mkdir()
    guard = FileGuard(read_root=read_root, write_root=read_root / "ws")
    shell = ShellRunner(repo_root=repo)
    reg = build_registry_for("self_healer", guard=guard, shell=shell)
    names = set(reg.names())
    assert "shell.run_tests" in names
    assert "shell.run_lint" in names


# ---------------------------------------------------------------------
# 9. audit_blob refuses to grant either tool to a dynamic profile
# ---------------------------------------------------------------------


def test_dynamic_profile_audit_rejects_shell_tools() -> None:
    blob = {
        "name": "rogue_runner",
        "system_prompt": "I would like to run tests, thank you.",
        "tools": ["file.read", "shell.run_tests"],
        "default_tier": "haiku",
        "step_budget": 8,
        "cost_cap_usd": 0.5,
        "notes": "n/a",
    }
    with pytest.raises(ProfileAuditError, match="forbidden"):
        audit_blob(
            blob,
            built_in_names=frozenset({"developer"}),
            available_tools=frozenset({"file.read", "shell.run_tests"}),
        )
