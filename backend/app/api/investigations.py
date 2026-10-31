from typing import Literal

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from app.api.deps import get_runtime
from app.database.models import RecoveryTask
from app.database.session import get_db
from app.errors import not_found
from app.schemas.investigation import (
    CreateInvestigationRequest,
    InvestigationList,
    InvestigationOut,
    ProgressOut,
    RecoveryTaskOut,
    ReportOut,
    UpdateRecoveryTask,
)
from app.schemas.settings import RuntimeSettings
from app.services import investigation_service, report_service

router = APIRouter(prefix="/api/investigations", tags=["investigations"])


@router.post("", response_model=InvestigationOut, status_code=202)
def create_investigation(
    body: CreateInvestigationRequest,
    request: Request,
    db: Session = Depends(get_db),
    runtime: RuntimeSettings = Depends(get_runtime),
) -> InvestigationOut:
    row = investigation_service.create(db, body.path, runtime)
    request.app.state.runner.submit(row.id)
    return investigation_service.to_out(db, row, runtime)


@router.get("", response_model=InvestigationList)
def list_investigations(
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    runtime: RuntimeSettings = Depends(get_runtime),
) -> InvestigationList:
    return investigation_service.list_all(db, runtime, limit, offset)


@router.get("/{investigation_id}", response_model=InvestigationOut)
def get_investigation(
    investigation_id: str,
    db: Session = Depends(get_db),
    runtime: RuntimeSettings = Depends(get_runtime),
) -> InvestigationOut:
    return investigation_service.to_out(
        db, investigation_service.get(db, investigation_id), runtime
    )


@router.get("/{investigation_id}/progress", response_model=ProgressOut)
def get_progress(investigation_id: str, db: Session = Depends(get_db)) -> ProgressOut:
    return investigation_service.progress(investigation_service.get(db, investigation_id))


@router.get("/{investigation_id}/report", response_model=ReportOut)
def get_report(
    investigation_id: str,
    db: Session = Depends(get_db),
    runtime: RuntimeSettings = Depends(get_runtime),
) -> ReportOut:
    row = investigation_service.get(db, investigation_id)
    return report_service.build_report(db, row, runtime)


@router.post("/{investigation_id}/reanalyze", response_model=InvestigationOut, status_code=202)
def reanalyze(
    investigation_id: str,
    request: Request,
    db: Session = Depends(get_db),
    runtime: RuntimeSettings = Depends(get_runtime),
) -> InvestigationOut:
    """Retry AI analysis from stored evidence, without repeating the deterministic scan."""
    investigation_service.claim_ai_rerun(db, investigation_id)
    request.app.state.runner.submit_ai(investigation_id)
    return investigation_service.to_out(
        db, investigation_service.get(db, investigation_id), runtime
    )


@router.get("/{investigation_id}/export")
def export_report(
    investigation_id: str,
    format: Literal["markdown", "json"] = "markdown",
    db: Session = Depends(get_db),
    runtime: RuntimeSettings = Depends(get_runtime),
) -> Response:
    row = investigation_service.get(db, investigation_id)
    report = report_service.build_report(db, row, runtime)
    if format == "json":
        content, media_type, extension = (
            report_service.export_json(report),
            "application/json",
            "json",
        )
    else:
        content, media_type, extension = (
            report_service.export_markdown(report),
            "text/markdown",
            "md",
        )
    filename = report_service.export_filename(report, extension)
    return Response(
        content,
        media_type=f"{media_type}; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.patch("/{investigation_id}/recovery-tasks/{task_id}", response_model=RecoveryTaskOut)
def update_recovery_task(
    investigation_id: str,
    task_id: str,
    body: UpdateRecoveryTask,
    db: Session = Depends(get_db),
) -> RecoveryTask:
    task = db.get(RecoveryTask, task_id)
    if task is None or task.investigation_id != investigation_id:
        raise not_found("The recovery task")
    task.status = body.status
    db.commit()
    return task
