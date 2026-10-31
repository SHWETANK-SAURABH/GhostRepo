from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    root = tmp_path / "workspace"
    root.mkdir()
    return root


@pytest.fixture
def settings(tmp_path: Path, workspace: Path) -> Settings:
    return Settings(
        _env_file=None,
        workspace_root=workspace,
        database_url=f"sqlite:///{(tmp_path / 'test.db').as_posix()}",
        ollama_endpoint="http://localhost:59999",
        ai_timeout_seconds=2,
        allowed_hosts=["testserver"],
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as test_client:
        yield test_client
