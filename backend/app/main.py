from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app import __version__
from app.api import dashboard, health, repositories
from app.api import settings as settings_api
from app.config import Settings
from app.database.session import Database
from app.errors import install_error_handlers
from app.schemas.common import ErrorResponse


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.database.init_schema()
        yield
        app.state.database.dispose()

    app = FastAPI(
        title="GhostRepo API",
        version=__version__,
        description="Local-first repository investigation and resurrection.",
        lifespan=lifespan,
        responses={
            404: {"model": ErrorResponse},
            422: {"model": ErrorResponse},
            500: {"model": ErrorResponse},
        },
    )
    app.state.settings = settings
    app.state.database = Database(settings.database_url)

    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PUT", "PATCH"],
        allow_headers=["Content-Type"],
    )
    install_error_handlers(app)

    app.include_router(health.router)
    app.include_router(dashboard.router)
    app.include_router(settings_api.router)
    app.include_router(repositories.router)
    return app


app = create_app()
