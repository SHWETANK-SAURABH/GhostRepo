"""Assemble reports from stored records and export them. Exports are redacted once more."""

import json
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import Evidence, Finding, Investigation, RecoveryTask
from app.schemas.investigation import (
    AiSection,
    EvidenceOut,
    FindingOut,
    HealthSection,
    RecoveryTaskOut,
    ReportOut,
)
from app.schemas.settings import RuntimeSettings
from app.security.secret_redaction import redact, redact_data
from app.services import investigation_service
from app.services.findings_engine import HEALTH_NOTE, SEVERITY_ORDER

_PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def build_report(db: Session, row: Investigation, runtime: RuntimeSettings) -> ReportOut:
    findings = db.scalars(select(Finding).where(Finding.investigation_id == row.id)).all()
    findings = sorted(findings, key=lambda f: SEVERITY_ORDER.get(f.severity, 9))
    evidence = db.scalars(
        select(Evidence).where(Evidence.investigation_id == row.id).order_by(Evidence.key)
    ).all()
    tasks = db.scalars(select(RecoveryTask).where(RecoveryTask.investigation_id == row.id)).all()
    tasks = sorted(tasks, key=lambda t: (_PRIORITY_ORDER.get(t.priority, 9), t.rank))

    ai_findings = [FindingOut.model_validate(f) for f in findings if f.origin == "ai"]
    has_ai = row.ai_status == "completed"
    if has_ai:
        provenance = "deterministic_and_ai"
    else:
        provenance = "deterministic" if evidence else "none"

    return ReportOut(
        investigation=investigation_service.to_out(db, row, runtime),
        profile=row.profile or {},
        health=HealthSection(score=row.health_score, note=HEALTH_NOTE),
        provenance=provenance,
        evidence=[_evidence_out(item) for item in evidence],
        verified_findings=[
            FindingOut.model_validate(f) for f in findings if f.origin == "deterministic"
        ],
        ai=AiSection(
            status=row.ai_status,
            model=row.ai_model,
            error=row.ai_error,
            summary=row.ai_summary,
            health_assessment=row.ai_health_assessment,
            findings=ai_findings,
            rejected=row.ai_rejected or [],
        ),
        recovery_tasks=[RecoveryTaskOut.model_validate(t) for t in tasks],
    )


def _evidence_out(item: Evidence) -> EvidenceOut:
    data = {k: v for k, v in (item.structured_data or {}).items() if k != "_kind"}
    return EvidenceOut(
        key=item.key,
        category=item.category,
        source_file=item.source_file,
        description=item.description,
        structured_data=data,
        detection_method=item.detection_method,
    )


def export_filename(report: ReportOut, extension: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", report.investigation.repository.name.lower()).strip("-")
    return f"ghostrepo-{slug or 'report'}-{report.investigation.id[:8]}.{extension}"


def export_json(report: ReportOut) -> str:
    return json.dumps(redact_data(report.model_dump(mode="json")), indent=2, ensure_ascii=False)


_PROVENANCE_LABEL = {
    "deterministic": "Deterministic analyzers only. No AI output is included.",
    "deterministic_and_ai": "Deterministic analyzers and a local AI model.",
    "none": "No analysis results are available.",
}


def _finding_lines(finding: FindingOut) -> list[str]:
    lines = [
        f"### [{finding.severity.upper()}] {finding.title}",
        "",
        finding.description,
        "",
        f"- Category: {finding.category}",
        f"- Confidence: {round(finding.confidence * 100)}%",
        f"- Detection method: {finding.detection_method}",
        f"- Evidence: {', '.join(finding.evidence_references) or 'none'}",
    ]
    if finding.source_file:
        lines.append(f"- Source: `{finding.source_file}`")
    lines += [f"- Suggested action: {finding.recommendation}", ""]
    return lines


def export_markdown(report: ReportOut) -> str:
    investigation = report.investigation
    profile = report.profile
    scout = profile.get("repository", {})
    git = profile.get("git", {})
    deps = profile.get("dependencies", {})

    lines = [
        f"# GhostRepo report: {investigation.repository.name}",
        "",
        f"- Investigation: `{investigation.id}`",
        f"- Status: {investigation.status}",
        f"- Created: {investigation.created_at.isoformat()}",
        f"- Results from: {_PROVENANCE_LABEL[report.provenance]}",
        f"- Health indicator: {report.health.score if report.health.score is not None else 'n/a'}",
        "",
        f"> {report.health.note}",
        "",
        "## Repository",
        "",
        f"- Primary language: {scout.get('primary_language') or 'unknown'}",
        f"- Frameworks: {', '.join(investigation.repository.detected_frameworks) or 'none detected'}",
        f"- Files scanned: {scout.get('file_count', 'unknown')}",
    ]
    if git.get("available") and git.get("latest_commit"):
        lines += [
            f"- Branch: {git.get('branch') or 'detached HEAD'}",
            f"- Commits: {git.get('commit_count')}",
            f"- Latest commit: {git['latest_commit']['date']}",
        ]
    else:
        lines.append("- Git history: not available")
    lines += [
        f"- Dependencies declared: {deps.get('dependency_count', 'unknown')}",
        "- Tests: discovered only, never executed",
        "",
    ]
    if deps.get("freshness_note"):
        lines += [f"> {deps['freshness_note']}", ""]

    lines += ["## Verified findings", ""]
    if report.verified_findings:
        for finding in report.verified_findings:
            lines += _finding_lines(finding)
    else:
        lines += ["None.", ""]

    lines += ["## AI analysis (generated by a local model, review before relying on it)", ""]
    if report.ai.status == "completed":
        lines += [
            f"Model: `{report.ai.model}`",
            "",
            report.ai.summary or "",
            "",
            report.ai.health_assessment or "",
            "",
        ]
        for finding in report.ai.findings:
            label = "Hypothesis" if finding.is_hypothesis else "Evidence-linked interpretation"
            lines += [f"**{label}**", "", *_finding_lines(finding)]
    else:
        lines += [f"AI analysis did not run to completion (status: {report.ai.status}).", ""]
        if report.ai.error:
            lines += [report.ai.error, ""]

    lines += ["## Resurrection plan", ""]
    for index, task in enumerate(report.recovery_tasks, start=1):
        origin = "AI suggestion" if task.origin == "ai" else "Rule-based"
        lines += [
            f"### {index}. {task.title}",
            "",
            f"- Priority: {task.priority}",
            f"- Status: {task.status}",
            f"- Source: {origin}",
            f"- Problem: {task.description}",
        ]
        if task.why_it_matters:
            lines.append(f"- Why it matters: {task.why_it_matters}")
        if task.solution:
            lines.append(f"- Recommended solution: {task.solution}")
        if task.files:
            lines.append(f"- Files: {', '.join(f'`{item}`' for item in task.files)}")
        if task.effort_estimate:
            lines.append(
                f"- Estimated effort (a rough estimate, not a measurement): {task.effort_estimate}"
            )
        lines += [f"- Verify: {step}" for step in task.verification_steps]
        lines.append("")

    lines += ["## Evidence", ""]
    for item in report.evidence:
        source = f" (`{item.source_file}`)" if item.source_file else ""
        lines.append(f"- `{item.key}` [{item.detection_method}]{source}: {item.description}")

    return redact("\n".join(lines)) + "\n"
