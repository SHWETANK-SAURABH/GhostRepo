from pathlib import Path

from fastapi import APIRouter, Depends

from app.api.deps import get_runtime
from app.demo_repo import DEMO_NAME, DemoRepoError, create_demo_repo
from app.errors import AppError
from app.schemas.repository import (
    CandidatesResponse,
    RepositoryCandidate,
    ValidateRepositoryRequest,
    ValidateRepositoryResponse,
)
from app.schemas.settings import RuntimeSettings
from app.services import repository_service

router = APIRouter(prefix="/api/repositories", tags=["repositories"])


@router.get("/candidates", response_model=CandidatesResponse)
def candidates(runtime: RuntimeSettings = Depends(get_runtime)) -> CandidatesResponse:
    return repository_service.list_candidates(runtime)


@router.post("/validate", response_model=ValidateRepositoryResponse)
def validate(
    body: ValidateRepositoryRequest, runtime: RuntimeSettings = Depends(get_runtime)
) -> ValidateRepositoryResponse:
    return repository_service.validate(body.path, runtime)


@router.post("/demo", response_model=RepositoryCandidate, status_code=201)
def create_demo(runtime: RuntimeSettings = Depends(get_runtime)) -> RepositoryCandidate:
    """Create the labeled sample repository in the workspace. Its contents are synthetic."""
    try:
        create_demo_repo(Path(runtime.workspace_root) / DEMO_NAME)
    except DemoRepoError as exc:
        raise AppError(409, "demo_conflict", str(exc)) from exc
    return RepositoryCandidate(name=DEMO_NAME, relative_path=DEMO_NAME, is_git=True, is_demo=True)
