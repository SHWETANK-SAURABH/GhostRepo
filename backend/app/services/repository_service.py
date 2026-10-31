"""Repository selection. Only direct children of the workspace are ever listed."""

import os
from pathlib import Path

from app.analyzers.git_historian import git_metadata_state
from app.schemas.repository import (
    CandidatesResponse,
    RepositoryCandidate,
    ValidateRepositoryResponse,
)
from app.schemas.settings import RuntimeSettings
from app.security.path_validation import (
    PathValidationError,
    relative_to_workspace,
    resolve_repository_path,
)

_MANIFESTS = {
    "requirements.txt",
    "pyproject.toml",
    "package.json",
    "cargo.toml",
    "go.mod",
    "pom.xml",
}
_MAX_CANDIDATES = 200


def list_candidates(runtime: RuntimeSettings) -> CandidatesResponse:
    root = Path(runtime.workspace_root)
    if not root.is_dir():
        return CandidatesResponse(workspace_available=False, candidates=[])

    candidates: list[RepositoryCandidate] = []
    with os.scandir(root) as entries:
        for entry in sorted(entries, key=lambda item: item.name.lower()):
            if len(candidates) >= _MAX_CANDIDATES:
                break
            if entry.name.startswith(".") or not entry.name.isprintable():
                continue
            if not entry.is_dir(follow_symlinks=False):
                continue
            path = Path(entry.path)
            candidates.append(
                RepositoryCandidate(
                    name=entry.name,
                    relative_path=entry.name,
                    is_git=git_metadata_state(path) == "present",
                )
            )
    return CandidatesResponse(workspace_available=True, candidates=candidates)


def validate(raw: str, runtime: RuntimeSettings) -> ValidateRepositoryResponse:
    try:
        path = resolve_repository_path(raw, runtime.workspace_root)
    except PathValidationError as exc:
        return ValidateRepositoryResponse(valid=False, code=exc.code, message=exc.message)

    try:
        top_level = [entry.name for entry in os.scandir(path)]
    except OSError:
        return ValidateRepositoryResponse(
            valid=False, code="unreadable", message="The directory could not be read."
        )

    names = [name for name in top_level if name.isprintable()]
    is_git = git_metadata_state(path) == "present"
    manifests = sorted(name for name in names if name.lower() in _MANIFESTS)
    has_readme = any(name.lower().startswith("readme") for name in names)

    if not names:
        message = "The directory is empty. An investigation will report little."
    elif is_git or manifests:
        message = "The repository is ready to investigate."
    else:
        message = (
            "This directory has no Git metadata or supported manifest. It can still be scanned."
        )

    return ValidateRepositoryResponse(
        valid=True,
        message=message,
        name=path.name,
        relative_path=relative_to_workspace(path, runtime.workspace_root),
        is_git=is_git,
        manifests=manifests,
        has_readme=has_readme,
    )
