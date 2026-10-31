from typing import Any

from pydantic import BaseModel


class ErrorBody(BaseModel):
    code: str
    message: str
    details: Any = None


class ErrorResponse(BaseModel):
    error: ErrorBody


class HealthResponse(BaseModel):
    status: str
    version: str
    database: str
    workspace_available: bool


class OllamaStatus(BaseModel):
    enabled: bool
    reachable: bool
    version: str | None = None
    model: str
    model_available: bool
    message: str


class OllamaModel(BaseModel):
    name: str
    size_bytes: int | None = None
    family: str | None = None
    parameter_size: str | None = None
    quantization: str | None = None


class OllamaModelsResponse(BaseModel):
    reachable: bool
    models: list[OllamaModel]
    message: str


class RecentInvestigation(BaseModel):
    id: str
    repository_name: str
    status: str
    ai_status: str
    health_score: int | None
    finding_count: int
    created_at: str


class DashboardSummary(BaseModel):
    investigations: int
    verified_findings: int
    pending_recovery_tasks: int
    average_health_score: int | None
    severity_counts: dict[str, int]
    recent: list[RecentInvestigation]
