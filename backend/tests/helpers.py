import os
import subprocess
from pathlib import Path

from app.analyzers.base import ScanContext, walk_repository
from app.config import DEFAULT_EXCLUDED_DIRS


def write_files(root: Path, files: dict[str, str]) -> None:
    for relative, content in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")


def make_repo(root: Path, files: dict[str, str]) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    write_files(root, files)
    return root


def scan(root: Path, **overrides):
    ctx = ScanContext(root=root, excluded_dirs=frozenset(DEFAULT_EXCLUDED_DIRS), **overrides)
    return ctx, walk_repository(ctx)


def git(root: Path, *args: str, date: str = "2024-01-15T12:00:00+00:00") -> str:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Ada Example",
        "GIT_AUTHOR_EMAIL": "ada@example.com",
        "GIT_COMMITTER_NAME": "Ada Example",
        "GIT_COMMITTER_EMAIL": "ada@example.com",
        "GIT_AUTHOR_DATE": date,
        "GIT_COMMITTER_DATE": date,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
    }
    result = subprocess.run(
        ["git", *args], cwd=root, env=env, check=True, capture_output=True, text=True
    )
    return result.stdout


def init_git(
    root: Path, message: str = "feat: first commit", date: str = "2024-01-15T12:00:00+00:00"
):
    git(root, "init", "-q", "-b", "main")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", message, date=date)


def kinds(result) -> set[str]:
    return {item.kind for item in result.evidence}
