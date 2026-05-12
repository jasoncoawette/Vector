"""Obsidian vault tool.

An Obsidian vault is just a directory of Markdown files. Vector treats
the vault as a scoped read/write surface with knowledge-base verbs on
top of the plain file ops:

  - obsidian.list                 names of every note (without .md)
  - obsidian.read(title|path)     read one note's body
  - obsidian.write(title, body)   create or overwrite
  - obsidian.append(title, body)  append (handy for daily notes)
  - obsidian.search(query)        substring search; returns top-k notes
                                   with snippet + line number
  - obsidian.backlinks(title)     notes that reference [[title]]

Scope guards: every operation resolves to a real path inside the vault
root. Symlink escape and `..` traversal are denied at the boundary.
This deliberately mirrors `FileGuard` rather than calling into it,
because the vault has note-shaped affordances FileGuard doesn't.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .errors import ToolDenied

MAX_NOTE_BYTES = 1 * 1024 * 1024  # 1MB per note
MAX_SEARCH_RESULTS = 20
SNIPPET_RADIUS = 80
SCAN_CAP = 5000  # don't walk vaults bigger than this many .md files

# Obsidian links: [[Title]] or [[Title|alias]] or [[Folder/Title]]
WIKILINK_RE = re.compile(r"\[\[([^\]\|#]+?)(?:\|[^\]]+)?(?:#[^\]]+)?\]\]")


@dataclass
class NoteHit:
    title: str
    path: str
    snippet: str
    line: int


@dataclass
class ObsidianVault:
    """One Obsidian vault rooted at `root`.

    The class is intentionally side-effect-light: no caching, no FS
    watcher. Search walks the tree on every call. For a vault under
    a few thousand notes this is fast enough; if it grows we'll add
    FTS5 later.
    """

    root: Path

    def __post_init__(self) -> None:
        self.root = self.root.expanduser().resolve()
        if not self.root.exists():
            self.root.mkdir(parents=True, exist_ok=True)
        if not self.root.is_dir():
            raise ValueError(f"vault root is not a directory: {self.root}")

    # --- path resolution ---------------------------------------------

    def _resolve(self, title_or_path: str) -> Path:
        """Turn 'My Note' or 'folder/My Note' or 'My Note.md' into an
        absolute path inside the vault. Refuses paths that escape."""
        if not title_or_path or not title_or_path.strip():
            raise ToolDenied("empty note name")
        raw = title_or_path.strip()
        # Strip leading slashes; Obsidian titles are always relative.
        raw = raw.lstrip("/\\")
        if not raw.endswith(".md"):
            raw = raw + ".md"
        candidate = (self.root / raw).resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError as e:
            raise ToolDenied(f"path outside vault: {raw}") from e
        # Reject paths that point to a different filesystem root via
        # absolute components (e.g. a backslash-prefixed Windows path).
        return candidate

    @staticmethod
    def _title_of(path: Path, root: Path) -> str:
        rel = path.relative_to(root)
        return rel.with_suffix("").as_posix()

    # --- read/write --------------------------------------------------

    def list_notes(self) -> list[str]:
        """Every .md file under the vault, as 'folder/Note' titles."""
        out: list[str] = []
        for i, p in enumerate(self.root.rglob("*.md")):
            if i >= SCAN_CAP:
                break
            try:
                out.append(self._title_of(p, self.root))
            except ValueError:
                continue
        return sorted(out)

    def read(self, title: str) -> dict:
        path = self._resolve(title)
        if not path.exists():
            raise ToolDenied(f"not found: {title}")
        if not path.is_file():
            raise ToolDenied(f"not a regular file: {title}")
        size = path.stat().st_size
        if size > MAX_NOTE_BYTES:
            text = path.read_text(encoding="utf-8", errors="replace")[: MAX_NOTE_BYTES]
            return {
                "title": self._title_of(path, self.root),
                "path": str(path),
                "size": size,
                "text": text,
                "truncated": True,
            }
        return {
            "title": self._title_of(path, self.root),
            "path": str(path),
            "size": size,
            "text": path.read_text(encoding="utf-8", errors="replace"),
            "truncated": False,
        }

    def write(self, title: str, body: str) -> dict:
        if len(body.encode("utf-8")) > MAX_NOTE_BYTES:
            raise ToolDenied(f"note exceeds {MAX_NOTE_BYTES} bytes")
        path = self._resolve(title)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        return {"title": self._title_of(path, self.root), "path": str(path), "bytes": len(body.encode("utf-8"))}

    def append(self, title: str, body: str) -> dict:
        path = self._resolve(title)
        existing = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
        joined = existing + ("\n" if existing and not existing.endswith("\n") else "") + body
        return self.write(title, joined)

    # --- search + links ---------------------------------------------

    def search(self, query: str, *, k: int = 5) -> list[NoteHit]:
        """Plain substring search (case-insensitive). Returns up to k
        hits with line number + a ±80-char snippet."""
        if not query or not query.strip():
            raise ToolDenied("empty query")
        k = max(1, min(k, MAX_SEARCH_RESULTS))
        needle = query.lower()
        hits: list[NoteHit] = []
        scanned = 0
        for path in self.root.rglob("*.md"):
            scanned += 1
            if scanned >= SCAN_CAP:
                break
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            lower = text.lower()
            idx = lower.find(needle)
            if idx < 0:
                continue
            line = text.count("\n", 0, idx) + 1
            start = max(0, idx - SNIPPET_RADIUS)
            end = min(len(text), idx + len(needle) + SNIPPET_RADIUS)
            snippet = text[start:end].replace("\n", " ").strip()
            hits.append(
                NoteHit(
                    title=self._title_of(path, self.root),
                    path=str(path),
                    snippet=snippet,
                    line=line,
                )
            )
            if len(hits) >= k:
                break
        return hits

    def backlinks(self, title: str) -> list[str]:
        """Notes that contain `[[title]]` (or `[[folder/title]]` /
        with alias / with anchor)."""
        target = title.strip().lower().removesuffix(".md")
        # Match by both the leaf name and the full relative path so
        # `[[Foo]]` and `[[bar/Foo]]` both resolve to bar/Foo.
        leaf = target.rsplit("/", 1)[-1]
        hits: list[str] = []
        scanned = 0
        for path in self.root.rglob("*.md"):
            scanned += 1
            if scanned >= SCAN_CAP:
                break
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            note_title = self._title_of(path, self.root)
            if note_title.lower() == target:
                # Don't list a note as its own backlink.
                continue
            for m in WIKILINK_RE.finditer(text):
                linked = m.group(1).strip().lower()
                if linked == target or linked == leaf or linked.endswith("/" + leaf):
                    hits.append(note_title)
                    break
        return sorted(set(hits))
