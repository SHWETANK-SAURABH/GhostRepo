"""Generated artifacts for an investigation: README drafts and patch proposals."""

import re
import time

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents import readme_generator
from app.analyzers.base import ScanContext
from app.api.deps import get_runtime, get_settings
from app.config import Settings
from app.database.models import GeneratedArtifact, Investigation, utcnow
from app.database.session import get_db
from app.errors import AppError, not_found
from app.schemas.artifact import (
    ApprovePatchRequest,
    GenerateReadmeRequest,
    PatchFileOut,
    PatchOut,
    ReadmeOut,
    SaveReadmeRequest,
)
from app.schemas.settings import RuntimeSettings
from app.security.path_validation import PathValidationError, resolve_repository_path
from app.services import investigation_service, patch_service

router = APIRouter(prefix="/api/investigations", tags=["artifacts"])

README = "readme_draft"
PATCH = "patch"


def _latest(db: Session, investigation_id: str, artifact_type: str) -> GeneratedArtifact | None:
    return db.scalar(
        select(GeneratedArtifact)
        .where(
            GeneratedArtifact.investigation_id == investigation_id,
            GeneratedArtifact.artifact_type == artifact_type,
        )
        .order_by(GeneratedArtifact.created_at.desc())
        .limit(1)
    )


def _require_analyzed(db: Session, investigation_id: str) -> Investigation:
    row = investigation_service.get(db, investigation_id)
    if not row.profile:
        raise AppError(
            409, "not_ready", "Wait for repository analysis to finish before generating this."
        )
    return row


def _readme_out(item: GeneratedArtifact) -> ReadmeOut:
    return ReadmeOut(
        id=item.id,
        content=item.content,
        origin=item.meta.get("origin", "deterministic"),
        ai_model=item.meta.get("ai_model"),
        warning=item.meta.get("warning"),
        unverified_sections=item.meta.get("unverified_sections", []),
        created_at=item.created_at,
    )


@router.post("/{investigation_id}/generate-readme", response_model=ReadmeOut, status_code=201)
def generate_readme(
    investigation_id: str,
    body: GenerateReadmeRequest,
    request: Request,
    db: Session = Depends(get_db),
    runtime: RuntimeSettings = Depends(get_runtime),
) -> ReadmeOut:
    row = _require_analyzed(db, investigation_id)
    client = None
    if body.use_ai:
        if not runtime.ai_enabled:
            raise AppError(409, "ai_disabled", "AI is disabled in Settings.")
        client = request.app.state.ollama_factory(runtime)

    draft = readme_generator.generate(row.profile, row.repository.name, client)
    artifact = GeneratedArtifact(
        investigation_id=row.id,
        artifact_type=README,
        content=draft.content,
        meta={
            "origin": draft.origin,
            "ai_model": draft.ai_model,
            "warning": draft.warning,
            "unverified_sections": draft.unverified_sections,
        },
    )
    db.add(artifact)
    db.commit()
    return _readme_out(artifact)


@router.get("/{investigation_id}/readme", response_model=ReadmeOut)
def get_readme(investigation_id: str, db: Session = Depends(get_db)) -> ReadmeOut:
    investigation_service.get(db, investigation_id)
    artifact = _latest(db, investigation_id, README)
    if artifact is None:
        raise not_found("A README draft")
    return _readme_out(artifact)


@router.put("/{investigation_id}/readme", response_model=ReadmeOut)
def save_readme(
    investigation_id: str, body: SaveReadmeRequest, db: Session = Depends(get_db)
) -> ReadmeOut:
    """Edits are stored as a new draft in GhostRepo. The repository's README is never touched."""
    row = _require_analyzed(db, investigation_id)
    previous = _latest(db, investigation_id, README)
    meta = {
        "origin": "edited",
        "ai_model": previous.meta.get("ai_model") if previous else None,
        "unverified_sections": previous.meta.get("unverified_sections", []) if previous else [],
    }
    artifact = GeneratedArtifact(
        investigation_id=row.id, artifact_type=README, content=body.content, meta=meta
    )
    db.add(artifact)
    db.commit()
    return _readme_out(artifact)


def _patch_out(item: GeneratedArtifact) -> PatchOut:
    return PatchOut(
        id=item.id,
        status=item.meta.get("status", "proposed"),
        diff=item.content,
        files=[PatchFileOut(**entry) for entry in item.meta.get("files", [])],
        refused_paths=item.meta.get("refused_paths", []),
        message=item.meta.get("message", ""),
        approved_at=item.meta.get("approved_at"),
        created_at=item.created_at,
    )


@router.post("/{investigation_id}/generate-patch", response_model=PatchOut, status_code=201)
def generate_patch(
    investigation_id: str,
    db: Session = Depends(get_db),
    runtime: RuntimeSettings = Depends(get_runtime),
    settings: Settings = Depends(get_settings),
) -> PatchOut:
    """Produce a proposal only. The repository is read to build the diff and never written."""
    row = _require_analyzed(db, investigation_id)
    try:
        root = resolve_repository_path(row.repository.local_path, runtime.workspace_root)
    except PathValidationError as exc:
        raise AppError(409, "repository_unavailable", exc.message) from exc

    ctx = ScanContext(
        root=root,
        max_file_size=runtime.max_file_size_bytes,
        excluded_dirs=frozenset(runtime.excluded_dirs),
        git_timeout=settings.git_timeout_seconds,
        deadline=time.monotonic() + runtime.analysis_timeout_seconds,
    )
    readme = _latest(db, investigation_id, README)
    files, refused = patch_service.propose(ctx, row.profile, readme.content if readme else None)
    message = (
        f"{len(files)} file(s) proposed. Nothing has been changed in the repository."
        if files
        else "No safe automatic change applies to this repository."
    )
    artifact = GeneratedArtifact(
        investigation_id=row.id,
        artifact_type=PATCH,
        content=patch_service.render_patch(files),
        meta={
            "status": "proposed",
            "files": patch_service.describe(files),
            "refused_paths": refused,
            "message": message,
            "approved_at": None,
        },
    )
    db.add(artifact)
    db.commit()
    return _patch_out(artifact)


@router.get("/{investigation_id}/patch", response_model=PatchOut)
def get_patch(investigation_id: str, db: Session = Depends(get_db)) -> PatchOut:
    investigation_service.get(db, investigation_id)
    artifact = _latest(db, investigation_id, PATCH)
    if artifact is None:
        raise not_found("A patch proposal")
    return _patch_out(artifact)


def _patch_artifact(db: Session, investigation_id: str, patch_id: str) -> GeneratedArtifact:
    artifact = db.get(GeneratedArtifact, patch_id)
    if (
        artifact is None
        or artifact.investigation_id != investigation_id
        or artifact.artifact_type != PATCH
    ):
        raise not_found("The patch proposal")
    return artifact


@router.post("/{investigation_id}/patch/{patch_id}/approve", response_model=PatchOut)
def approve_patch(
    investigation_id: str,
    patch_id: str,
    body: ApprovePatchRequest,
    db: Session = Depends(get_db),
) -> PatchOut:
    """Record that a person reviewed the diff, which unlocks download. Nothing is applied."""
    artifact = _patch_artifact(db, investigation_id, patch_id)
    if not body.confirm:
        raise AppError(400, "confirmation_required", "Approval must be confirmed explicitly.")
    if not artifact.content:
        raise AppError(409, "empty_patch", "This proposal has no changes to approve.")
    artifact.meta = {**artifact.meta, "status": "approved", "approved_at": utcnow().isoformat()}
    db.commit()
    return _patch_out(artifact)


@router.get("/{investigation_id}/patch/{patch_id}/download")
def download_patch(investigation_id: str, patch_id: str, db: Session = Depends(get_db)) -> Response:
    artifact = _patch_artifact(db, investigation_id, patch_id)
    if artifact.meta.get("status") != "approved":
        raise AppError(409, "not_approved", "Approve this patch before downloading it.")
    repository = investigation_service.get(db, investigation_id).repository.name
    slug = re.sub(r"[^a-z0-9]+", "-", repository.lower()).strip("-") or "repository"
    return Response(
        artifact.content,
        media_type="text/x-patch; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="ghostrepo-{slug}.patch"'},
    )
