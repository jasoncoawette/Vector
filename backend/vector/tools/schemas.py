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
