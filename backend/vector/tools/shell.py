"""Sandboxed shell-execution tools for the self_healer agent.

These are the first tools in the codebase that fork external processes.
Every layer is paranoid by design:

* **Scope check**: every `path` arg is resolved against `repo_root` and
  must `relative_to(repo_root)` cleanly. No traversal, no absolute
  escapes.
* **Argv only**: `subprocess.run` is always called with `shell=False`
  and a fully-constructed list. Never a string. Never user-controlled
  metacharacters.
* **Minimal env**: only `PATH`, `HOME`, `LANG`, `LC_ALL`, and any
  explicitly-allowed `VECTOR_*` keys are forwarded. The full os.environ
  (which holds the Anthropic API key and OAuth secrets) never leaks
  into a child.
* **Hard timeout**: every call passes `timeout=self.timeout_s`. A
  `TimeoutExpired` becomes a `ShellTimeout` ToolError.
* **Output capping**: stdout + stderr are truncated to
  `MAX_OUTPUT_BYTES`, keeping the *tail* (failures usually print last).

Tools registered:
  shell.run_tests  — pytest / vitest
  shell.run_lint   — ruff / svelte-check

Both names are in `FORBIDDEN_DYNAMIC_TOOLS`. Only built-in employees
(self_healer) may have them in their allowlist; dynamic profiles
produced by prompt_engineer cannot request them.
"""
from __future__ import annotations

import os
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

DEFAULT_TIMEOUT_S = 60
MAX_OUTPUT_BYTES = 4_000

# Env keys we forward to children. Anything outside this set (especially
# VECTOR_* secrets like the Anthropic API key) is excluded.
_ENV_ALLOWLIST: frozenset[str] = frozenset({
    "PATH",
    "HOME",
    "LANG",
    "LC_ALL",
})
# Explicit VECTOR_* allowlist. Empty by design — we have nothing the
# child genuinely needs, and keeping this empty enforces the no-secrets
# rule. Add narrowly if a future runner needs e.g. VECTOR_BUILD_HASH.
_VECTOR_ENV_ALLOWLIST: frozenset[str] = frozenset()


class ShellError(RuntimeError):
    """Base class for shell-tool failures."""


class ShellTimeout(ShellError):
    """Raised when a subprocess exceeds its hard timeout."""


class ShellScopeError(ShellError):
    """Raised when a path argument escapes repo_root."""


@dataclass
class ShellResult:
    exit_code: int
    stdout_tail: str
    stderr_tail: str
    elapsed_s: float
    passed: int | None = None
    failed: int | None = None

    def to_dict(self) -> dict:
        return {
            "exit_code": self.exit_code,
            "stdout_tail": self.stdout_tail,
            "stderr_tail": self.stderr_tail,
            "elapsed_s": self.elapsed_s,
            "passed": self.passed,
            "failed": self.failed,
        }


# Match pytest's summary line: "===== 5 passed, 1 failed in 0.42s ====="
_PYTEST_SUMMARY = re.compile(
    r"(?P<count>\d+)\s+(?P<status>passed|failed|error|errors)",
    re.IGNORECASE,
)


def _parse_pytest_counts(text: str) -> tuple[int | None, int | None]:
    """Best-effort extract of `passed` / `failed` from pytest's summary
    line. Returns (None, None) when no summary is found.

    pytest prints variants like:
        ===== 5 passed in 0.42s =====
        ===== 3 passed, 1 failed in 0.42s =====
        1 passed in 0.00s
    The summary always ends with " in <time>s" so we look for a line
    that has both a count+status pair and "in <number>s"."""
    if not text:
        return (None, None)
    # Scan tail-first; the summary is always near the bottom.
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    in_time = re.compile(r"\bin\s+\d+(?:\.\d+)?s\b")
    for line in reversed(lines):
        if not in_time.search(line):
            continue
        matches = list(_PYTEST_SUMMARY.finditer(line))
        if not matches:
            continue
        passed: int | None = None
        failed: int | None = None
        for m in matches:
            n = int(m.group("count"))
            status = m.group("status").lower()
            if status == "passed":
                passed = n
            elif status in {"failed", "error", "errors"}:
                # If both failed and errors appear, sum them.
                failed = (failed or 0) + n
        if passed is not None or failed is not None:
            return (passed, failed)
    return (None, None)


def _cap_tail(data: bytes, limit: int = MAX_OUTPUT_BYTES) -> str:
    """Decode the last `limit` bytes of `data`. Failures usually print
    near the end, so the tail is the useful part."""
    if not data:
        return ""
    tail = data[-limit:]
    return tail.decode("utf-8", errors="replace")


def _build_child_env() -> dict[str, str]:
    """Return a minimal environment for child processes.

    Only forwards the explicit allowlist. NEVER pass `os.environ` whole;
    that would leak `VECTOR_ANTHROPIC_API_KEY`, OAuth tokens, etc."""
    env: dict[str, str] = {}
    for key in _ENV_ALLOWLIST:
        val = os.environ.get(key)
        if val is not None:
            env[key] = val
    for key in _VECTOR_ENV_ALLOWLIST:
        val = os.environ.get(key)
        if val is not None:
            env[key] = val
    # Most pytest setups expect at least a PATH; if the host has none
    # we still pass an empty value rather than letting subprocess
    # inherit the parent's untrimmed environment.
    env.setdefault("PATH", "/usr/local/bin:/usr/bin:/bin")
    return env


@dataclass
class ShellRunner:
    """Pinned-scope launcher for test/lint subprocesses.

    All commands run with `cwd=repo_root` (or a subdir of it), no shell,
    a minimal env, and a hard timeout. Paths are normalized through
    `_resolve_in_root` so callers can't slip in `..` or absolute paths
    outside the repo.
    """

    repo_root: Path
    timeout_s: int = DEFAULT_TIMEOUT_S

    def __post_init__(self) -> None:
        self.repo_root = Path(self.repo_root).expanduser().resolve()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _resolve_in_root(self, raw: str) -> Path:
        """Resolve `raw` against repo_root and confirm it stays inside.

        Returns the absolute resolved path on success. Raises
        ShellScopeError on any escape (parent traversal, absolute path
        outside repo, symlink chain leaving repo, etc.).
        """
        if not raw:
            raise ShellScopeError("empty path")
        # If the caller passed an absolute path, anchor on it directly
        # so the resolve-then-relative-to check catches /etc/passwd. If
        # relative, join against repo_root first.
        candidate = Path(raw)
        if candidate.is_absolute():
            resolved = candidate.resolve()
        else:
            resolved = (self.repo_root / candidate).resolve()
        try:
            resolved.relative_to(self.repo_root)
        except ValueError as exc:
            raise ShellScopeError(
                f"path escapes repo_root: {raw!r}"
            ) from exc
        return resolved

    def _run(
        self,
        argv: list[str],
        *,
        cwd: Path,
    ) -> ShellResult:
        """Common subprocess wrapper. NEVER pass a string here; argv
        must already be a list. NEVER set shell=True."""
        assert isinstance(argv, list), "argv must be a list (shell=False contract)"
        assert all(isinstance(a, str) for a in argv), "argv entries must be strings"

        env = _build_child_env()
        start = time.monotonic()
        try:
            completed = subprocess.run(  # noqa: S603 — argv only, shell=False
                argv,
                shell=False,
                cwd=str(cwd),
                env=env,
                capture_output=True,
                timeout=self.timeout_s,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            elapsed = time.monotonic() - start
            stdout_tail = _cap_tail(exc.stdout or b"")
            stderr_tail = _cap_tail(exc.stderr or b"")
            raise ShellTimeout(
                f"command timed out after {self.timeout_s}s: {argv[0]} "
                f"(elapsed={elapsed:.2f}s) stdout_tail={stdout_tail!r} "
                f"stderr_tail={stderr_tail!r}"
            ) from exc

        elapsed = time.monotonic() - start
        return ShellResult(
            exit_code=int(completed.returncode),
            stdout_tail=_cap_tail(completed.stdout or b""),
            stderr_tail=_cap_tail(completed.stderr or b""),
            elapsed_s=round(elapsed, 4),
        )

    # ------------------------------------------------------------------
    # Public tool entrypoints
    # ------------------------------------------------------------------

    def run_tests(
        self,
        *,
        path: str | None,
        framework: str,
    ) -> ShellResult:
        """Run the project's test runner.

        framework='pytest': `python -m pytest <path or 'tests/unit'> -q`
        framework='vitest': `pnpm test <path>` inside repo_root/frontend
        """
        if framework not in {"pytest", "vitest"}:
            raise ShellError(f"unsupported framework: {framework!r}")

        if framework == "pytest":
            target_raw = path if path else "tests/unit"
            target = self._resolve_in_root(target_raw)
            # Pass the path relative to repo_root for cleaner output.
            rel = target.relative_to(self.repo_root)
            argv = ["python", "-m", "pytest", str(rel), "-q"]
            result = self._run(argv, cwd=self.repo_root)
            passed, failed = _parse_pytest_counts(
                result.stdout_tail + "\n" + result.stderr_tail
            )
            result.passed = passed
            result.failed = failed
            return result

        # framework == "vitest"
        frontend = (self.repo_root / "frontend").resolve()
        try:
            frontend.relative_to(self.repo_root)
        except ValueError as exc:  # pragma: no cover — defensive
            raise ShellScopeError("frontend dir outside repo_root") from exc
        argv: list[str] = ["pnpm", "test"]
        if path:
            target = self._resolve_in_root(path)
            # vitest is invoked from the frontend dir; pass the path
            # relative to that dir.
            try:
                rel = target.relative_to(frontend)
            except ValueError:
                rel = target.relative_to(self.repo_root)
            argv.append(str(rel))
        return self._run(argv, cwd=frontend)

    def run_lint(
        self,
        *,
        path: str,
        tool: str,
    ) -> ShellResult:
        """Run a linter.

        tool='ruff': `python -m ruff check <path>`
        tool='svelte-check': `pnpm check` inside repo_root/frontend
                              (svelte-check doesn't take a path arg).
        """
        if tool not in {"ruff", "svelte-check"}:
            raise ShellError(f"unsupported lint tool: {tool!r}")

        if tool == "ruff":
            target = self._resolve_in_root(path)
            rel = target.relative_to(self.repo_root)
            argv = ["python", "-m", "ruff", "check", str(rel)]
            return self._run(argv, cwd=self.repo_root)

        # tool == "svelte-check": runs the whole frontend; the `path`
        # is still validated to keep the contract uniform, but svelte-check
        # doesn't accept a path argument.
        _ = self._resolve_in_root(path)  # scope check only
        frontend = (self.repo_root / "frontend").resolve()
        argv = ["pnpm", "check"]
        return self._run(argv, cwd=frontend)
