from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_runtime, get_settings
from app.config import Settings
from app.database.session import get_db
from app.schemas.settings import RuntimeSettings
from app.services import settings_service

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("", response_model=RuntimeSettings)
def read_settings(runtime: RuntimeSettings = Depends(get_runtime)) -> RuntimeSettings:
    return runtime


@router.put("", response_model=RuntimeSettings)
def update_settings(
    body: RuntimeSettings,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> RuntimeSettings:
    return settings_service.save(db, settings, body)
