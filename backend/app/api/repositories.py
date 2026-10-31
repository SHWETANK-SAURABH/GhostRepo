from fastapi import APIRouter, Depends

from app.api.deps import get_runtime
from app.schemas.repository import (
    CandidatesResponse,
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
