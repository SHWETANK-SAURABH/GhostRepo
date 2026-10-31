from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class GenerateReadmeRequest(BaseModel):
    use_ai: bool = False


class SaveReadmeRequest(BaseModel):
    content: str = Field(min_length=1, max_length=200_000)


class ReadmeOut(BaseModel):
    id: str
    content: str
    origin: Literal["deterministic", "deterministic_and_ai", "edited"]
    ai_model: str | None = None
    warning: str | None = None
    unverified_sections: list[str] = []
    created_at: datetime


class PatchFileOut(BaseModel):
    path: str
    change_type: Literal["create", "modify"]
    explanation: str
    additions: int
    deletions: int


class PatchOut(BaseModel):
    id: str
    status: Literal["proposed", "approved"]
    diff: str
    files: list[PatchFileOut]
    refused_paths: list[str] = []
    message: str
    approved_at: str | None = None
    created_at: datetime


class ApprovePatchRequest(BaseModel):
    confirm: bool
