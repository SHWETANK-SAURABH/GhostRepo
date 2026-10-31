"""Environment configuration. Values a user can change at runtime live in settings_service."""

from pathlib import Path
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BACKEND_DIR.parent

DEFAULT_EXCLUDED_DIRS = [
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    "dist",
    "build",
    "target",
    ".next",
    "coverage",
]

CsvList = Annotated[list[str], NoDecode]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GHOSTREPO_", env_file=".env", extra="ignore")

    workspace_root: Path = PROJECT_DIR / "workspace"
    database_url: str = f"sqlite:///{(BACKEND_DIR / 'data' / 'ghostrepo.db').as_posix()}"

    ai_enabled: bool = True
    ollama_endpoint: str = "http://127.0.0.1:11434"
    ollama_model: str = "gemma3:4b"
    ollama_allowed_hosts: CsvList = [
        "localhost",
        "127.0.0.1",
        "::1",
        "ollama",
        "host.docker.internal",
    ]
    ai_timeout_seconds: int = 300
    ai_context_tokens: int = 8192

    max_file_size_bytes: int = 1_000_000
    max_scan_depth: int = 12
    max_scan_files: int = 20_000
    excluded_dirs: CsvList = DEFAULT_EXCLUDED_DIRS
    analysis_timeout_seconds: int = 120
    git_timeout_seconds: int = 20
    max_concurrent_investigations: int = 2

    cors_origins: CsvList = ["http://localhost:3000", "http://127.0.0.1:3000"]
    allowed_hosts: CsvList = ["localhost", "127.0.0.1", "backend"]

    @field_validator(
        "ollama_allowed_hosts", "excluded_dirs", "cors_origins", "allowed_hosts", mode="before"
    )
    @classmethod
    def _split_csv(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value
