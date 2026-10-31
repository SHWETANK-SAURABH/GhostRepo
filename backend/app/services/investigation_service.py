"""Investigation records: creation, lookup and API representations."""

from pathlib import Path

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, joinedload

from app.agents.orchestrator import ACTIVE_STATUSES, initial_stages
from app.database.models import Finding, Investigation, Repository
from app.errors import AppError, not_found
from app.schemas.investigation import (
    InvestigationList,
    InvestigationOut,
    ProgressOut,
    RepositoryOut,
    StageOut,
)
from app.schemas.settings import RuntimeSettings
from app.security.path_validation import PathValidationError, resolve_repository_path

MAX_QUEUED = 20
_DONE_STAGES = {"completed", "failed", "skipped"}


def create(db: Session, raw_path: str, runtime: RuntimeSettings) -> Investigation:
    try:
        path = resolve_repository_path(raw_path, runtime.workspace_root)
    except PathValidationError as exc:
        status = 404 if exc.code == "not_found" else 400
        raise AppError(status, exc.code, exc.message) from exc

    active = db.scalar(
        select(func.count())
        .select_from(Investigation)
        .where(Investigation.status.in_(ACTIVE_STATUSES))
    )
    if (active or 0) >= MAX_QUEUED:
        raise AppError(429, "too_many_investigations", "Too many investigations are in progress.")

    repository = db.scalar(select(Repository).where(Repository.local_path == str(path)))
    if repository is None:
        repository = Repository(name=path.name[:255], local_path=str(path))
        db.add(repository)
        db.flush()
    else:
        running = db.scalar(
            select(Investigation.id).where(
                Investigation.repository_id == repository.id,
                Investigation.status.in_(ACTIVE_STATUSES),
            )
        )
        if running:
            raise AppError(
                409,
                "already_running",
                "This repository is already being investigated.",
                {"investigation_id": running},
            )

    investigation = Investigation(
        repository=repository, status="queued", ai_status="pending", stages=initial_stages()
    )
    db.add(investigation)
    db.commit()
    return investigation


def get(db: Session, investigation_id: str) -> Investigation:
    row = db.scalar(
        select(Investigation)
        .options(joinedload(Investigation.repository))
        .where(Investigation.id == investigation_id)
    )
    if row is None:
        raise not_found("The investigation")
    return row


def claim_ai_rerun(db: Session, investigation_id: str) -> None:
    """Atomically move to queued, so two retry requests cannot both start."""
    row = get(db, investigation_id)
    if row.status != "completed":
        raise AppError(
            409, "not_ready", "AI analysis can be retried once the investigation has completed."
        )
    claimed = db.execute(
        update(Investigation)
        .where(
            Investigation.id == investigation_id,
            Investigation.ai_status.not_in(("queued", "running")),
        )
        .values(ai_status="queued", ai_error=None)
    )
    if claimed.rowcount == 0:
        db.rollback()
        raise AppError(409, "already_running", "AI analysis is already running.")
    db.commit()
    db.refresh(row)


def _relative_path(repository: Repository, runtime: RuntimeSettings) -> str | None:
    try:
        return (
            Path(repository.local_path)
            .relative_to(Path(runtime.workspace_root).resolve())
            .as_posix()
        )
    except ValueError:
        return None


def to_out(db: Session, row: Investigation, runtime: RuntimeSettings) -> InvestigationOut:
    counts = dict(
        db.execute(
            select(Finding.origin, func.count())
            .where(Finding.investigation_id == row.id)
            .group_by(Finding.origin)
        ).all()
    )
    repository = row.repository
    return InvestigationOut(
        id=row.id,
        repository=RepositoryOut(
            id=repository.id,
            name=repository.name,
            relative_path=_relative_path(repository, runtime),
            detected_languages=repository.detected_languages or [],
            detected_frameworks=repository.detected_frameworks or [],
        ),
        status=row.status,
        current_stage=row.current_stage,
        stages=[StageOut(**stage) for stage in row.stages],
        created_at=row.created_at,
        started_at=row.started_at,
        completed_at=row.completed_at,
        error_message=row.error_message,
        health_score=row.health_score,
        ai_status=row.ai_status,
        ai_model=row.ai_model,
        ai_error=row.ai_error,
        verified_finding_count=counts.get("deterministic", 0),
        ai_finding_count=counts.get("ai", 0),
    )


def list_all(db: Session, runtime: RuntimeSettings, limit: int, offset: int) -> InvestigationList:
    rows = db.scalars(
        select(Investigation)
        .options(joinedload(Investigation.repository))
        .order_by(Investigation.created_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    total = db.scalar(select(func.count()).select_from(Investigation)) or 0
    return InvestigationList(items=[to_out(db, row, runtime) for row in rows], total=total)


def progress(row: Investigation) -> ProgressOut:
    stages = [StageOut(**stage) for stage in row.stages]
    done = sum(1 for stage in stages if stage.status in _DONE_STAGES)
    return ProgressOut(
        id=row.id,
        status=row.status,
        current_stage=row.current_stage,
        stages=stages,
        percent=round(done / len(stages) * 100) if stages else 0,
        error_message=row.error_message,
        ai_status=row.ai_status,
        ai_error=row.ai_error,
    )
