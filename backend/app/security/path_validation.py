"""Confine repository access to the workspace, and proposed patches to their repository."""

import re
from pathlib import Path, PurePosixPath

from app.security.secret_redaction import is_secret_file

_WINDOWS_RESERVED = {"con", "prn", "aux", "nul"} | {
    f"{name}{digit}" for name in ("com", "lpt") for digit in range(1, 10)
}
# git~1 is the 8.3 short name of .git on Windows.
_GIT_SHORT_NAME = re.compile(r"^git~\d+$", re.IGNORECASE)


class PathValidationError(ValueError):
    """The message is safe to return: it never echoes a resolved server path."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def resolve_repository_path(raw: str, workspace_root: str | Path) -> Path:
    """Resolve user input to a directory strictly inside the workspace, following symlinks."""
    if not raw or not raw.strip():
        raise PathValidationError("empty_path", "Enter a repository path.")
    if "\x00" in raw or len(raw) > 4096:
        raise PathValidationError("invalid_path", "The repository path is not valid.")

    try:
        root = Path(workspace_root).resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise PathValidationError(
            "workspace_unavailable", "The configured workspace root is not available."
        ) from exc

    candidate = Path(raw.strip()).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate

    # Check before and after resolving, so a missing path outside the root reads as "outside".
    try:
        resolved = candidate.resolve(strict=False)
    except (OSError, RuntimeError, ValueError) as exc:
        raise PathValidationError("invalid_path", "The repository path is not valid.") from exc

    if not resolved.is_relative_to(root) or resolved == root:
        raise PathValidationError(
            "outside_workspace", "The repository must be inside the configured workspace root."
        )
    if ":" in str(resolved.relative_to(root)):
        raise PathValidationError("invalid_path", "The repository path is not valid.")
    if not resolved.exists():
        raise PathValidationError("not_found", "No directory exists at that path.")
    if not resolved.is_dir():
        raise PathValidationError("not_a_directory", "The path is not a directory.")
    return resolved


def relative_to_workspace(path: Path, workspace_root: str | Path) -> str:
    return path.resolve().relative_to(Path(workspace_root).resolve()).as_posix()


def validate_patch_path(repo_root: Path, relative: str) -> str:
    """Return a normalized repository-relative path a patch may touch, or raise."""
    if not relative or "\x00" in relative or len(relative) > 1024:
        raise PathValidationError("invalid_patch_path", "The patch path is not valid.")

    normalized = relative.replace("\\", "/")
    pure = PurePosixPath(normalized)
    if pure.is_absolute() or re.match(r"^[A-Za-z]:", normalized) or normalized.startswith("//"):
        raise PathValidationError("patch_path_escape", "Patch paths must be relative.")
    if ".." in pure.parts:
        raise PathValidationError("patch_path_escape", "Patch paths must stay in the repository.")

    for part in pure.parts:
        # Windows ignores trailing dots and spaces, so ".git." opens .git.
        stripped = part.rstrip(". ").lower()
        if stripped == ".git" or part.lower() == ".git" or _GIT_SHORT_NAME.match(stripped):
            raise PathValidationError("patch_path_forbidden", "Patches may not modify .git.")
        if stripped.split(".")[0] in _WINDOWS_RESERVED or ":" in part:
            raise PathValidationError("invalid_patch_path", "The patch path is not valid.")

    if is_secret_file(normalized):
        raise PathValidationError(
            "patch_path_forbidden", "Patches may not modify secrets or credentials."
        )

    root = repo_root.resolve()
    target = (root / normalized).resolve(strict=False)
    if not target.is_relative_to(root) or target == root:
        raise PathValidationError("patch_path_escape", "Patch paths must stay in the repository.")
    return pure.as_posix()
