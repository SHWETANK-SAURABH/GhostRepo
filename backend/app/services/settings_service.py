"""Runtime settings: environment defaults overlaid with values saved from the UI."""

from pathlib import Path
from urllib.parse import urlsplit

from sqlalchemy.orm import Session

from app.config import Settings
from app.database.models import AppSetting
from app.errors import AppError
from app.schemas.settings import RuntimeSettings

_KEY = "runtime"


def defaults(settings: Settings) -> RuntimeSettings:
    return RuntimeSettings(
        ollama_endpoint=settings.ollama_endpoint,
        ollama_model=settings.ollama_model,
        ai_enabled=settings.ai_enabled,
        workspace_root=str(settings.workspace_root),
        max_file_size_bytes=settings.max_file_size_bytes,
        excluded_dirs=list(settings.excluded_dirs),
        analysis_timeout_seconds=settings.analysis_timeout_seconds,
    )


def load(db: Session, settings: Settings) -> RuntimeSettings:
    base = defaults(settings).model_dump()
    row = db.get(AppSetting, _KEY)
    if row:
        base.update(row.value)
    return RuntimeSettings.model_validate(base)


def save(db: Session, settings: Settings, new: RuntimeSettings) -> RuntimeSettings:
    validate_endpoint(new.ollama_endpoint, settings)
    new = new.model_copy(update={"workspace_root": validate_workspace_root(new.workspace_root)})
    row = db.get(AppSetting, _KEY)
    if row:
        row.value = new.model_dump()
    else:
        db.add(AppSetting(key=_KEY, value=new.model_dump()))
    db.commit()
    return new


def validate_endpoint(endpoint: str, settings: Settings) -> None:
    """Keep repository evidence on this machine: only allowlisted local hosts may receive it."""
    parts = urlsplit(endpoint)
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise AppError(422, "invalid_endpoint", "The Ollama endpoint must be an http(s) URL.")
    if parts.username or parts.password:
        raise AppError(422, "invalid_endpoint", "The Ollama endpoint must not contain credentials.")
    if parts.hostname not in settings.ollama_allowed_hosts:
        raise AppError(
            422,
            "endpoint_not_allowed",
            "This host is not allowed. To keep source data local, add it to "
            "GHOSTREPO_OLLAMA_ALLOWED_HOSTS on the server if it is yours.",
        )


def validate_workspace_root(raw: str) -> str:
    try:
        root = Path(raw).expanduser().resolve(strict=True)
    except (OSError, RuntimeError, ValueError) as exc:
        raise AppError(422, "invalid_workspace", "The workspace root does not exist.") from exc
    if not root.is_dir():
        raise AppError(422, "invalid_workspace", "The workspace root is not a directory.")
    if root == Path(root.anchor) or root == Path.home().resolve():
        raise AppError(
            422,
            "workspace_too_broad",
            "Choose a dedicated folder, not a drive root or your home directory.",
        )
    return str(root)
