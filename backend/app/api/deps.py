from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.config import Settings
from app.database.session import get_db
from app.schemas.settings import RuntimeSettings
from app.services import settings_service
from app.services.ollama_service import OllamaClient


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_runtime(
    db: Session = Depends(get_db), settings: Settings = Depends(get_settings)
) -> RuntimeSettings:
    return settings_service.load(db, settings)


def get_ollama(request: Request, runtime: RuntimeSettings = Depends(get_runtime)) -> OllamaClient:
    return request.app.state.ollama_factory(runtime)
