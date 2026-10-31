"""SQLAlchemy persistence models."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def new_id() -> str:
    return uuid.uuid4().hex


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Repository(Base):
    __tablename__ = "repositories"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(255))
    local_path: Mapped[str] = mapped_column(Text, unique=True)
    detected_languages: Mapped[list[str]] = mapped_column(JSON, default=list)
    detected_frameworks: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    investigations: Mapped[list["Investigation"]] = relationship(back_populates="repository")


class Investigation(Base):
    __tablename__ = "investigations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    repository_id: Mapped[str] = mapped_column(ForeignKey("repositories.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    current_stage: Mapped[str | None] = mapped_column(String(40), nullable=True)
    stages: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    profile: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    health_score: Mapped[int | None] = mapped_column(Integer, nullable=True)

    ai_status: Mapped[str] = mapped_column(String(20), default="pending")
    ai_model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ai_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_health_assessment: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_rejected: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)

    repository: Mapped[Repository] = relationship(back_populates="investigations")
    evidence: Mapped[list["Evidence"]] = relationship(
        back_populates="investigation", cascade="all, delete-orphan"
    )
    findings: Mapped[list["Finding"]] = relationship(
        back_populates="investigation", cascade="all, delete-orphan"
    )
    recovery_tasks: Mapped[list["RecoveryTask"]] = relationship(
        back_populates="investigation", cascade="all, delete-orphan"
    )
    artifacts: Mapped[list["GeneratedArtifact"]] = relationship(
        back_populates="investigation", cascade="all, delete-orphan"
    )


class Evidence(Base):
    __tablename__ = "evidence"
    __table_args__ = (UniqueConstraint("investigation_id", "key", name="uq_evidence_key"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    investigation_id: Mapped[str] = mapped_column(ForeignKey("investigations.id"), index=True)
    key: Mapped[str] = mapped_column(String(40))
    category: Mapped[str] = mapped_column(String(40))
    source_file: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str] = mapped_column(Text)
    structured_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    detection_method: Mapped[str] = mapped_column(String(120))

    investigation: Mapped[Investigation] = relationship(back_populates="evidence")


class Finding(Base):
    __tablename__ = "findings"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    investigation_id: Mapped[str] = mapped_column(ForeignKey("investigations.id"), index=True)
    rule_id: Mapped[str | None] = mapped_column(String(60), nullable=True)
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(20))
    category: Mapped[str] = mapped_column(String(40))
    confidence: Mapped[float] = mapped_column(Float)
    evidence_references: Mapped[list[str]] = mapped_column(JSON, default=list)
    is_hypothesis: Mapped[bool] = mapped_column(default=False)
    recommendation: Mapped[str] = mapped_column(Text)
    source_file: Mapped[str | None] = mapped_column(Text, nullable=True)
    detection_method: Mapped[str] = mapped_column(String(120))
    origin: Mapped[str] = mapped_column(String(20), default="deterministic", index=True)

    investigation: Mapped[Investigation] = relationship(back_populates="findings")


class RecoveryTask(Base):
    __tablename__ = "recovery_tasks"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    investigation_id: Mapped[str] = mapped_column(ForeignKey("investigations.id"), index=True)
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)
    why_it_matters: Mapped[str | None] = mapped_column(Text, nullable=True)
    solution: Mapped[str | None] = mapped_column(Text, nullable=True)
    files: Mapped[list[str]] = mapped_column(JSON, default=list)
    effort_estimate: Mapped[str | None] = mapped_column(String(40), nullable=True)
    verification_steps: Mapped[list[str]] = mapped_column(JSON, default=list)
    priority: Mapped[str] = mapped_column(String(20))
    rank: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    evidence_references: Mapped[list[str]] = mapped_column(JSON, default=list)
    origin: Mapped[str] = mapped_column(String(20), default="deterministic")

    investigation: Mapped[Investigation] = relationship(back_populates="recovery_tasks")


class GeneratedArtifact(Base):
    __tablename__ = "generated_artifacts"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    investigation_id: Mapped[str] = mapped_column(ForeignKey("investigations.id"), index=True)
    artifact_type: Mapped[str] = mapped_column(String(40), index=True)
    content: Mapped[str] = mapped_column(Text)
    meta: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    investigation: Mapped[Investigation] = relationship(back_populates="artifacts")


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
