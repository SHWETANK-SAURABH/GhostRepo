from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.database.models import Finding, Investigation, RecoveryTask
from app.database.session import get_db
from app.schemas.common import DashboardSummary, RecentInvestigation

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

_SEVERITIES = ["critical", "high", "medium", "low", "info"]
_RECENT_LIMIT = 8


@router.get("", response_model=DashboardSummary)
def summary(db: Session = Depends(get_db)) -> DashboardSummary:
    verified = Finding.origin == "deterministic"
    severity_rows = db.execute(
        select(Finding.severity, func.count()).where(verified).group_by(Finding.severity)
    ).all()
    counts = {severity: 0 for severity in _SEVERITIES}
    counts.update({severity: count for severity, count in severity_rows})

    average = db.scalar(
        select(func.avg(Investigation.health_score)).where(Investigation.health_score.is_not(None))
    )
    recent = db.scalars(
        select(Investigation)
        .options(joinedload(Investigation.repository))
        .order_by(Investigation.created_at.desc())
        .limit(_RECENT_LIMIT)
    ).all()
    finding_counts = dict(
        db.execute(
            select(Finding.investigation_id, func.count())
            .where(Finding.investigation_id.in_([item.id for item in recent]))
            .group_by(Finding.investigation_id)
        ).all()
    )

    return DashboardSummary(
        investigations=db.scalar(select(func.count()).select_from(Investigation)) or 0,
        verified_findings=sum(counts.values()),
        pending_recovery_tasks=db.scalar(
            select(func.count()).select_from(RecoveryTask).where(RecoveryTask.status == "pending")
        )
        or 0,
        average_health_score=round(average) if average is not None else None,
        severity_counts=counts,
        recent=[
            RecentInvestigation(
                id=item.id,
                repository_name=item.repository.name,
                status=item.status,
                ai_status=item.ai_status,
                health_score=item.health_score,
                finding_count=finding_counts.get(item.id, 0),
                created_at=item.created_at.isoformat(),
            )
            for item in recent
        ],
    )
