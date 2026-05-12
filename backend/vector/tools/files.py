from __future__ import annotations

import os
import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path

from .errors import NeedsConfirm, ToolDenied

MAX_INLINE_BYTES = 50 * 1024 * 1024
PREVIEW_BYTES = 4096
CONFIRM_TTL_S = 60

HARD_BLOCK_NAMES = frozenset(
    {".ssh", ".aws", ".gnupg", "Keychains", "Login.keychain-db"}
)


@dataclass
class FileGuard:
    read_root: Path
    write_root: Path
    _pending: dict[str, tuple[float, str, str]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.read_root = self.read_root.expanduser().resolve()
        self.write_root = self.write_root.expanduser().resolve()
        self.write_root.mkdir(parents=True, exist_ok=True)
        if not self._is_inside(self.write_root, self.read_root):
            raise ValueError("write_root must be inside read_root")

    @staticmethod
    def _is_inside(child: Path, parent: Path) -> bool:
        try:
            child.relative_to(parent)
            return True
        except ValueError:
            return False

    def _resolve(self, raw: str) -> Path:
        if not raw:
            raise ToolDenied("empty path")
        p = Path(raw).expanduser()
        try:
            real = p.resolve(strict=False)
        except (OSError, RuntimeError) as e:
            raise ToolDenied(f"path resolve failed: {e}") from e
        return real

    def _check_hard_block(self, real: Path) -> None:
        parts = set(real.parts)
        if parts & HARD_BLOCK_NAMES:
            raise ToolDenied(f"hard-blocked path: {real}")

    def _check_read_scope(self, real: Path) -> None:
        self._check_hard_block(real)
        if not self._is_inside(real, self.read_root):
            raise ToolDenied(f"path outside read scope: {real}")

    def _check_write_scope(self, real: Path, confirm: bool) -> None:
        self._check_hard_block(real)
        if self._is_inside(real, self.write_root):
            return
        if not self._is_inside(real, self.read_root):
            raise ToolDenied(f"path outside any scope: {real}")
        if not confirm:
            raise ToolDenied(
                f"write outside workspace requires confirm=true: {real}"
            )

    def _issue_token(self, op: str, path: str) -> str:
        token = secrets.token_urlsafe(16)
        self._pending[token] = (time.time(), op, path)
        return token

    def _consume_token(self, token: str, op: str, path: str) -> None:
        entry = self._pending.pop(token, None)
        if entry is None:
            raise ToolDenied("invalid or expired confirm token")
        ts, saved_op, saved_path = entry
        if time.time() - ts > CONFIRM_TTL_S:
            raise ToolDenied("confirm token expired")
        if saved_op != op or saved_path != path:
            raise ToolDenied("confirm token does not match op or path")

    def read(self, path: str) -> dict:
        real = self._resolve(path)
        self._check_read_scope(real)
        if not real.exists():
            raise ToolDenied(f"not found: {real}")
        if not real.is_file():
            raise ToolDenied(f"not a regular file: {real}")
        size = real.stat().st_size
        with real.open("rb") as fh:
            head = fh.read(PREVIEW_BYTES)
        if b"\x00" in head:
            return {"path": str(real), "size": size, "binary": True, "text": None}
        if size > MAX_INLINE_BYTES:
            return {
                "path": str(real),
                "size": size,
                "binary": False,
                "text": head.decode("utf-8", errors="replace"),
                "summary_mode": True,
            }
        return {
            "path": str(real),
            "size": size,
            "binary": False,
            "text": real.read_text(encoding="utf-8", errors="replace"),
        }

    def write(self, path: str, content: str, *, confirm: bool = False) -> dict:
        real = self._resolve(path)
        self._check_write_scope(real, confirm=confirm)
        real.parent.mkdir(parents=True, exist_ok=True)
        real.write_text(content, encoding="utf-8")
        return {"path": str(real), "bytes": len(content.encode("utf-8"))}

    def request_delete(self, path: str) -> str:
        real = self._resolve(path)
        self._check_read_scope(real)
        if not real.exists():
            raise ToolDenied(f"not found: {real}")
        token = self._issue_token("delete", str(real))
        raise NeedsConfirm(f"delete needs confirm: {real}", token)

    def confirm_delete(self, path: str, token: str) -> dict:
        real = self._resolve(path)
        self._check_read_scope(real)
        self._consume_token(token, "delete", str(real))
        if not real.exists():
            raise ToolDenied(f"not found: {real}")
        if not real.is_file():
            raise ToolDenied(f"refuse to delete non-file: {real}")
        os.remove(real)
        return {"path": str(real), "deleted": True}
