"""Investigation orchestrator: one coordinator running deterministic tools in the background.

Deterministic results are saved before any model is called, so an AI failure cannot lose them.
"""

import logging
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, TypeVar

from sqlalchemy import delete, select, update

from app.agents import ghost_analyst, resurrection_planner
from app.analyzers import (
    configuration_analyzer,
    dependency_analyzer,
    documentation_analyzer,
    git_historian,
    repository_scout,
    test_discovery,
)
from app.analyzers.base import AnalyzerResult, ScanContext, ScanTimeout, walk_repository
from app.config import Settings
from app.database.models import Evidence, Finding, Investigation, RecoveryTask, Repository, utcnow
from app.database.session import Database
from app.models.analysis import GhostAnalysis
from app.schemas.settings import RuntimeSettings
from app.security.path_validation import PathValidationError, resolve_repository_path
from app.security.secret_redaction import redact_data
from app.services import evidence_service, findings_engine, settings_service
from app.services.ollama_service import OllamaClient

logger = logging.getLogger(__name__)

T = TypeVar("T")

STAGES = [
    ("discovery", "Repository discovery"),
    ("git", "Git history analysis"),
    ("dependencies", "Dependency inspection"),
    ("configuration", "Configuration inspection"),
    ("documentation", "Documentation inspection"),
    ("tests", "Test discovery"),
    ("ai", "AI analysis"),
    ("report", "Report generation"),
]
ACTIVE_STATUSES = ("queued", "running")


def initial_stages() -> list[dict[str, Any]]:
    return [
        {"key": key, "label": label, "status": "pending", "message": None} for key, label in STAGES
    ]


def evidence_dicts(rows: list[Evidence]) -> list[dict[str, Any]]:
    return [
        {
            "key": row.key,
            "kind": row.structured_data.get("_kind", ""),
            "category": row.category,
            "description": row.description,
            "source_file": row.source_file,
            "structured_data": {k: v for k, v in row.structured_data.items() if k != "_kind"},
            "detection_method": row.detection_method,
        }
        for row in rows
    ]


class InvestigationRunner:
    def __init__(
        self,
        database: Database,
        settings: Settings,
        ollama_factory: Callable[[RuntimeSettings], OllamaClient],
    ) -> None:
        self.database = database
        self.settings = settings
        self.ollama_factory = ollama_factory
        self._pool = ThreadPoolExecutor(
            max_workers=settings.max_concurrent_investigations, thread_name_prefix="investigation"
        )

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)

    def submit(self, investigation_id: str) -> None:
        self._pool.submit(self._guarded, investigation_id, self._run)

    def submit_ai(self, investigation_id: str) -> None:
        self._pool.submit(self._guarded_ai, investigation_id)

    def recover_interrupted(self) -> None:
        """Work does not survive a restart. Say so, instead of showing a run that never ends."""
        message = "The server restarted before this investigation finished."
        with self.database.scope() as db:
            db.execute(
                update(Investigation)
                .where(Investigation.status.in_(ACTIVE_STATUSES))
                .values(status="interrupted", error_message=message, completed_at=utcnow())
            )
            db.execute(
                update(Investigation)
                .where(Investigation.ai_status.in_(("queued", "running")))
                .values(
                    ai_status="failed",
                    ai_error="The server restarted during AI analysis. You can retry it.",
                )
            )

    def _guarded(self, investigation_id: str, work: Callable[[str], None]) -> None:
        try:
            work(investigation_id)
        except ScanTimeout:
            self._fail(
                investigation_id,
                "The analysis time limit was reached. Raise it in Settings or exclude more "
                "folders, then investigate again.",
            )
        except Exception:
            logger.exception("Investigation stopped unexpectedly")
            self._fail(investigation_id, "An unexpected error stopped the investigation.")

    def _guarded_ai(self, investigation_id: str) -> None:
        try:
            self._ai_stage(investigation_id)
        except Exception:
            logger.exception("AI analysis stopped unexpectedly")
            with self.database.scope() as db:
                row = db.get(Investigation, investigation_id)
                if row:
                    row.ai_status = "failed"
                    row.ai_error = "An unexpected error stopped AI analysis. You can retry it."
            self._set_stage(investigation_id, "ai", "failed", "AI analysis stopped unexpectedly.")

    def _fail(self, investigation_id: str, message: str) -> None:
        with self.database.scope() as db:
            row = db.get(Investigation, investigation_id)
            if row is None:
                return
            row.status = "failed"
            row.error_message = message
            row.completed_at = utcnow()
            if row.ai_status in ("pending", "queued"):
                row.ai_status = "skipped"
            row.stages = [
                {**stage, "status": "failed", "message": message}
                if stage["status"] == "running"
                else stage
                for stage in row.stages
            ]

    def _set_stage(
        self, investigation_id: str, key: str, status: str, message: str | None = None
    ) -> None:
        with self.database.scope() as db:
            row = db.get(Investigation, investigation_id)
            if row is None:
                return
            if status == "running":
                row.current_stage = key
            row.stages = [
                {**stage, "status": status, "message": message} if stage["key"] == key else stage
                for stage in row.stages
            ]

    def _stage(
        self,
        investigation_id: str,
        key: str,
        failures: list[str],
        work: Callable[[], T],
    ) -> T | None:
        """Run one stage. A failure is recorded and the remaining stages still run."""
        self._set_stage(investigation_id, key, "running")
        try:
            result = work()
        except ScanTimeout:
            raise
        except Exception:
            logger.exception("Stage %s failed", key)
            label = dict(STAGES)[key]
            failures.append(label)
            self._set_stage(investigation_id, key, "failed", f"{label} failed on this repository.")
            return None
        self._set_stage(investigation_id, key, "completed")
        return result

    def _run(self, investigation_id: str) -> None:
        with self.database.scope() as db:
            row = db.get(Investigation, investigation_id)
            if row is None:
                return
            row.status = "running"
            row.started_at = utcnow()
            repository_path = row.repository.local_path
            repository_id = row.repository_id
            runtime = settings_service.load(db, self.settings)

        # Validate again: the path may have become a symlink since the request was accepted.
        try:
            root = resolve_repository_path(repository_path, runtime.workspace_root)
        except PathValidationError as exc:
            self._set_stage(investigation_id, "discovery", "running")
            self._fail(investigation_id, exc.message)
            return

        ctx = self._context(root, runtime)
        failures: list[str] = []
        results: dict[str, AnalyzerResult] = {}

        def scout() -> Any:
            inventory = walk_repository(ctx)
            results["repository"] = repository_scout.analyze(ctx, inventory)
            return inventory

        inventory = self._stage(investigation_id, "discovery", failures, scout)
        if inventory is None:
            self._fail(investigation_id, "The repository could not be scanned.")
            return

        def stage(key: str, name: str, work: Callable[[], AnalyzerResult]) -> None:
            ctx.check_deadline()
            result = self._stage(investigation_id, key, failures, work)
            if result is not None:
                results[name] = result

        stage("git", "git", lambda: git_historian.analyze(ctx))
        stage("dependencies", "dependencies", lambda: dependency_analyzer.analyze(ctx, inventory))
        stage(
            "configuration",
            "configuration",
            lambda: configuration_analyzer.analyze(ctx, inventory),
        )
        stage(
            "documentation",
            "documentation",
            lambda: documentation_analyzer.analyze(ctx, inventory),
        )
        dependency_facts = results["dependencies"].facts if "dependencies" in results else {}
        dependency_names = {dep["name"] for dep in dependency_facts.get("dependencies", [])}
        pytest_configured = any(
            meta.get("has_pytest_config") for meta in dependency_facts.get("metadata", {}).values()
        )
        stage(
            "tests",
            "tests",
            lambda: test_discovery.analyze(ctx, inventory, dependency_names, pytest_configured),
        )

        self._persist_deterministic(investigation_id, repository_id, results)
        self._ai_stage(investigation_id)
        self._finish(investigation_id, failures)

    def _context(self, root: Path, runtime: RuntimeSettings) -> ScanContext:
        return ScanContext(
            root=root,
            max_file_size=runtime.max_file_size_bytes,
            max_depth=self.settings.max_scan_depth,
            max_files=self.settings.max_scan_files,
            excluded_dirs=frozenset(runtime.excluded_dirs),
            git_timeout=self.settings.git_timeout_seconds,
            deadline=time.monotonic() + runtime.analysis_timeout_seconds,
        )

    def _persist_deterministic(
        self, investigation_id: str, repository_id: str, results: dict[str, AnalyzerResult]
    ) -> None:
        normalized = evidence_service.normalize(list(results.values()))
        dicts = [
            {
                "key": item.key,
                "kind": item.kind,
                "category": item.category,
                "description": item.description,
                "source_file": item.source_file,
                "structured_data": item.structured_data,
                "detection_method": item.detection_method,
            }
            for item in normalized
        ]
        findings = findings_engine.build_findings(dicts)
        tasks = resurrection_planner.build_plan(findings)
        profile = {name: redact_data(result.facts) for name, result in results.items()}

        with self.database.scope() as db:
            investigation = db.get(Investigation, investigation_id)
            investigation.profile = profile
            investigation.health_score = findings_engine.health_score(findings, dicts)
            db.add_all(
                Evidence(
                    investigation_id=investigation_id,
                    key=item.key,
                    category=item.category,
                    source_file=item.source_file,
                    description=item.description,
                    structured_data={**item.structured_data, "_kind": item.kind},
                    detection_method=item.detection_method,
                )
                for item in normalized
            )
            db.add_all(
                Finding(
                    investigation_id=investigation_id,
                    rule_id=finding.rule_id,
                    title=finding.title,
                    description=finding.description,
                    severity=finding.severity,
                    category=finding.category,
                    confidence=finding.confidence,
                    evidence_references=finding.evidence_references,
                    is_hypothesis=False,
                    recommendation=finding.recommendation,
                    source_file=finding.source_file,
                    detection_method=finding.detection_method,
                    origin="deterministic",
                )
                for finding in findings
            )
            db.add_all(
                RecoveryTask(
                    investigation_id=investigation_id,
                    title=task.title,
                    description=task.description,
                    why_it_matters=task.why_it_matters,
                    solution=task.solution,
                    files=task.files,
                    effort_estimate=task.effort_estimate,
                    verification_steps=task.verification_steps,
                    priority=task.priority,
                    rank=rank,
                    evidence_references=task.evidence_references,
                    origin="deterministic",
                )
                for rank, task in enumerate(tasks)
            )

            repository = db.get(Repository, repository_id)
            scout_facts = profile.get("repository", {})
            dependency_facts = profile.get("dependencies", {})
            repository.detected_languages = [
                item["name"] for item in scout_facts.get("languages", [])
            ]
            repository.detected_frameworks = sorted(
                {*scout_facts.get("frameworks", []), *dependency_facts.get("frameworks", [])}
            )

    def _ai_stage(self, investigation_id: str) -> None:
        self._set_stage(investigation_id, "ai", "running")
        with self.database.scope() as db:
            row = db.get(Investigation, investigation_id)
            runtime = settings_service.load(db, self.settings)
            row.ai_model = runtime.ollama_model
            if not runtime.ai_enabled:
                row.ai_status = "disabled"
                row.ai_error = None
            else:
                row.ai_status = "running"
                row.ai_error = None
            evidence = evidence_dicts(
                list(
                    db.scalars(
                        select(Evidence).where(Evidence.investigation_id == investigation_id)
                    )
                )
            )

        if not runtime.ai_enabled:
            self._set_stage(investigation_id, "ai", "skipped", "AI is disabled in Settings.")
            return

        client = self.ollama_factory(runtime)
        status = client.status()
        if not status.reachable or not status.model_available:
            self._record_ai_failure(investigation_id, "unavailable", status.message)
            return

        try:
            result = ghost_analyst.analyze(client, evidence)
        except ghost_analyst.AnalystFailure as exc:
            self._record_ai_failure(investigation_id, "failed", str(exc))
            return

        self._store_ai_result(investigation_id, runtime.ollama_model, result, evidence)
        self._set_stage(investigation_id, "ai", "completed")

    def _record_ai_failure(self, investigation_id: str, status: str, message: str) -> None:
        with self.database.scope() as db:
            row = db.get(Investigation, investigation_id)
            row.ai_status = status
            row.ai_error = message
        self._set_stage(investigation_id, "ai", "failed", message)

    def _store_ai_result(
        self,
        investigation_id: str,
        model: str,
        result: ghost_analyst.AnalystResult,
        evidence: list[dict[str, Any]],
    ) -> None:
        analysis: GhostAnalysis = result.analysis
        sources = {item["key"]: item["source_file"] for item in evidence}
        method = f"local-ai:{model}"[:120]

        with self.database.scope() as db:
            db.execute(
                delete(Finding).where(
                    Finding.investigation_id == investigation_id, Finding.origin == "ai"
                )
            )
            db.execute(
                delete(RecoveryTask).where(
                    RecoveryTask.investigation_id == investigation_id, RecoveryTask.origin == "ai"
                )
            )
            row = db.get(Investigation, investigation_id)
            row.ai_status = "completed"
            row.ai_error = None
            row.ai_model = model
            row.ai_summary = analysis.summary
            row.ai_health_assessment = analysis.health_assessment
            row.ai_rejected = [item.model_dump() for item in result.rejected]

            db.add_all(
                Finding(
                    investigation_id=investigation_id,
                    title=finding.title,
                    description=finding.description,
                    severity=finding.severity,
                    category=finding.category,
                    confidence=finding.confidence,
                    evidence_references=finding.evidence_ids,
                    is_hypothesis=finding.is_hypothesis,
                    recommendation=finding.recommendation,
                    source_file=next(
                        (sources[ref] for ref in finding.evidence_ids if sources.get(ref)), None
                    ),
                    detection_method=method,
                    origin="ai",
                )
                for finding in analysis.findings
            )
            offset = len(
                db.scalars(
                    select(RecoveryTask.id).where(RecoveryTask.investigation_id == investigation_id)
                ).all()
            )
            db.add_all(
                RecoveryTask(
                    investigation_id=investigation_id,
                    title=task.title,
                    description=task.description,
                    priority=task.priority,
                    rank=offset + index,
                    evidence_references=task.related_evidence_ids,
                    origin="ai",
                )
                for index, task in enumerate(analysis.recovery_plan)
            )

    def _finish(self, investigation_id: str, failures: list[str]) -> None:
        self._set_stage(investigation_id, "report", "running")
        with self.database.scope() as db:
            row = db.get(Investigation, investigation_id)
            # One commit, so a client never sees a finished run with a stage still running.
            row.status = "completed"
            row.completed_at = utcnow()
            row.current_stage = None
            row.stages = [
                {**stage, "status": "completed", "message": None}
                if stage["key"] == "report"
                else stage
                for stage in row.stages
            ]
            if failures:
                row.error_message = (
                    f"Some stages failed, so this report is incomplete: {', '.join(failures)}."
                )
