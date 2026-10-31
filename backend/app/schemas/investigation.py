from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class CreateInvestigationRequest(BaseModel):
    path: str = Field(max_length=4096)


class RepositoryOut(BaseModel):
    """local_path is deliberately absent: the API reports only workspace-relative paths."""

    id: str
    name: str
    relative_path: str | None
    detected_languages: list[str]
    detected_frameworks: list[str]


class StageOut(BaseModel):
    key: str
    label: str
    status: str
    message: str | None = None


class InvestigationOut(BaseModel):
    id: str
    repository: RepositoryOut
    status: str
    current_stage: str | None
    stages: list[StageOut]
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    error_message: str | None
    health_score: int | None
    ai_status: str
    ai_model: str | None
    ai_error: str | None
    verified_finding_count: int
    ai_finding_count: int


class InvestigationList(BaseModel):
    items: list[InvestigationOut]
    total: int


class ProgressOut(BaseModel):
    id: str
    status: str
    current_stage: str | None
    stages: list[StageOut]
    percent: int
    error_message: str | None
    ai_status: str
    ai_error: str | None


class EvidenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    category: str
    source_file: str | None
    description: str
    structured_data: dict[str, Any]
    detection_method: str


class FindingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    rule_id: str | None
    title: str
    description: str
    severity: str
    category: str
    confidence: float
    evidence_references: list[str]
    is_hypothesis: bool
    recommendation: str
    source_file: str | None
    detection_method: str
    origin: str


class RecoveryTaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    description: str
    why_it_matters: str | None
    solution: str | None
    files: list[str]
    effort_estimate: str | None
    verification_steps: list[str]
    priority: str
    rank: int
    status: str
    evidence_references: list[str]
    origin: str


class UpdateRecoveryTask(BaseModel):
    status: Literal["pending", "in_progress", "done", "dismissed"]


class AiSection(BaseModel):
    status: str
    model: str | None
    error: str | None
    summary: str | None
    health_assessment: str | None
    findings: list[FindingOut]
    rejected: list[dict[str, Any]]


class HealthSection(BaseModel):
    score: int | None
    note: str


class ReportOut(BaseModel):
    investigation: InvestigationOut
    profile: dict[str, Any]
    health: HealthSection
    provenance: Literal["deterministic", "deterministic_and_ai", "none"]
    evidence: list[EvidenceOut]
    verified_findings: list[FindingOut]
    ai: AiSection
    recovery_tasks: list[RecoveryTaskOut]
