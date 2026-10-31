from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app import __version__
from app.api.deps import get_ollama, get_runtime
from app.database.session import get_db
from app.schemas.common import HealthResponse, OllamaModelsResponse, OllamaStatus
from app.schemas.settings import RuntimeSettings
from app.services.ollama_service import OllamaClient

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health(
    db: Session = Depends(get_db), runtime: RuntimeSettings = Depends(get_runtime)
) -> HealthResponse:
    try:
        db.execute(text("SELECT 1"))
        database = "ok"
    except SQLAlchemyError:
        database = "error"
    return HealthResponse(
        status="ok" if database == "ok" else "degraded",
        version=__version__,
        database=database,
        workspace_available=Path(runtime.workspace_root).is_dir(),
    )


@router.get("/ollama/status", response_model=OllamaStatus)
def ollama_status(
    ollama: OllamaClient = Depends(get_ollama), runtime: RuntimeSettings = Depends(get_runtime)
) -> OllamaStatus:
    return ollama.status(enabled=runtime.ai_enabled)


@router.get("/ollama/models", response_model=OllamaModelsResponse)
def ollama_models(ollama: OllamaClient = Depends(get_ollama)) -> OllamaModelsResponse:
    return ollama.models_response()
