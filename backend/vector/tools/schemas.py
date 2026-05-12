from __future__ import annotations

from pydantic import BaseModel, Field


class FileReadArgs(BaseModel):
    path: str = Field(min_length=1)


class FileWriteArgs(BaseModel):
    path: str = Field(min_length=1)
    content: str
    confirm: bool = False


class FileDeleteArgs(BaseModel):
    path: str = Field(min_length=1)
    confirm_token: str | None = None


class MemorySearchArgs(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    kind: str | None = Field(default=None, max_length=64)
    k: int = Field(default=5, ge=1, le=20)


class MemoryAddArgs(BaseModel):
    kind: str = Field(min_length=1, max_length=64)
    text: str = Field(min_length=1, max_length=20_000)
    meta: dict | None = None


# --- Obsidian vault tool ---------------------------------------------


class ObsidianReadArgs(BaseModel):
    title: str = Field(min_length=1, max_length=512)


class ObsidianWriteArgs(BaseModel):
    title: str = Field(min_length=1, max_length=512)
    body: str = Field(max_length=1_000_000)


class ObsidianAppendArgs(BaseModel):
    title: str = Field(min_length=1, max_length=512)
    body: str = Field(min_length=1, max_length=1_000_000)


class ObsidianSearchArgs(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    k: int = Field(default=5, ge=1, le=20)


class ObsidianBacklinksArgs(BaseModel):
    title: str = Field(min_length=1, max_length=512)


class ObsidianListArgs(BaseModel):
    pass
