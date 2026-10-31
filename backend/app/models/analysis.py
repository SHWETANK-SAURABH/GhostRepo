"""The contract a model's reply must satisfy before anything is stored."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Severity = Literal["critical", "high", "medium", "low", "info"]
FindingCategory = Literal[
    "dependency", "documentation", "testing", "configuration", "architecture", "maintenance"
]
Priority = Literal["high", "medium", "low"]


class AiFinding(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=2000)
    severity: Severity
    category: FindingCategory
    evidence_ids: list[str] = Field(max_length=20)
    recommendation: str = Field(min_length=1, max_length=1500)
    confidence: float = Field(ge=0, le=1)
    is_hypothesis: bool


class AiRecoveryTask(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=1500)
    priority: Priority
    related_evidence_ids: list[str] = Field(max_length=20)


class GhostAnalysis(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    summary: str = Field(min_length=1, max_length=3000)
    health_assessment: str = Field(min_length=1, max_length=3000)
    findings: list[AiFinding] = Field(max_length=30)
    recovery_plan: list[AiRecoveryTask] = Field(max_length=20)


class RejectedItem(BaseModel):
    item_type: Literal["finding", "recovery_task", "statement"]
    title: str
    reason: str
