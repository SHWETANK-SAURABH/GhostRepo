from pydantic import BaseModel, Field


class ValidateRepositoryRequest(BaseModel):
    path: str = Field(max_length=4096)


class RepositoryCandidate(BaseModel):
    name: str
    relative_path: str
    is_git: bool


class CandidatesResponse(BaseModel):
    workspace_available: bool
    candidates: list[RepositoryCandidate]


class ValidateRepositoryResponse(BaseModel):
    valid: bool
    code: str | None = None
    message: str
    name: str | None = None
    relative_path: str | None = None
    is_git: bool = False
    manifests: list[str] = []
    has_readme: bool = False
