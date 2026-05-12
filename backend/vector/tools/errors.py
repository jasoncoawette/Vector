from __future__ import annotations


class ToolError(Exception):
    """Base class for tool failures."""


class ToolDenied(ToolError):
    """Hard refusal. No retry, no confirm. Caller is told why."""


class NeedsConfirm(ToolError):
    """Soft refusal. Caller must re-issue with a confirm token."""

    def __init__(self, reason: str, token: str) -> None:
        super().__init__(reason)
        self.token = token
