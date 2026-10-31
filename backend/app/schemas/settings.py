"""Settings a user can change from the UI."""

import re

from pydantic import BaseModel, Field, field_validator

_MODEL_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}$")
_DIR_NAME = re.compile(r"^[^/\\\x00]{1,100}$")


class RuntimeSettings(BaseModel):
    ollama_endpoint: str = Field(min_length=1, max_length=300)
    ollama_model: str
    ai_enabled: bool
    workspace_root: str = Field(min_length=1, max_length=1000)
    max_file_size_bytes: int = Field(ge=1_024, le=50_000_000)
    excluded_dirs: list[str] = Field(max_length=200)
    analysis_timeout_seconds: int = Field(ge=5, le=3_600)

    @field_validator("ollama_model")
    @classmethod
    def _valid_model(cls, value: str) -> str:
        if not _MODEL_NAME.fullmatch(value):
            raise ValueError("Model names may use letters, digits and . _ : / - only.")
        return value

    @field_validator("excluded_dirs")
    @classmethod
    def _valid_dirs(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value if item.strip()]
        for item in cleaned:
            if not _DIR_NAME.fullmatch(item) or item in {".", ".."}:
                raise ValueError("Excluded directories must be plain directory names.")
        return cleaned
