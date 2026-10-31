from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app import __version__
from app.agents.orchestrator import InvestigationRunner
from app.api import dashboard, health, investigations, reports, repositories
from app.api import settings as settings_api
from app.config import Settings
from app.database.session import Database
from app.errors import install_error_handlers
from app.schemas.common import ErrorResponse
from app.schemas.settings import RuntimeSettings
from app.services.ollama_service import OllamaClient


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.database.init_schema()
        app.state.runner.recover_interrupted()
        yield
        app.state.runner.shutdown()
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
    app.state.ollama_transport = None

    def ollama_factory(runtime: RuntimeSettings) -> OllamaClient:
        return OllamaClient(
            endpoint=runtime.ollama_endpoint,
            model=runtime.ollama_model,
            timeout_seconds=settings.ai_timeout_seconds,
            context_tokens=settings.ai_context_tokens,
            transport=app.state.ollama_transport,
        )

    app.state.ollama_factory = ollama_factory
    app.state.runner = InvestigationRunner(app.state.database, settings, ollama_factory)

    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PUT", "PATCH"],
        allow_headers=["Content-Type"],
    )
    install_error_handlers(app)

    @app.middleware("http")
    async def reject_cross_site_writes(request: Request, call_next) -> Response:
        """CORS does not stop a bodyless POST from another site, so check the Origin here."""
        origin = request.headers.get("origin")
        if (
            request.method not in {"GET", "HEAD", "OPTIONS"}
            and origin is not None
            and origin not in settings.cors_origins
        ):
            return JSONResponse(
                {
                    "error": {
                        "code": "forbidden_origin",
                        "message": "Requests from this origin are not allowed.",
                        "details": None,
                    }
                },
                status_code=403,
            )
        return await call_next(request)

    app.include_router(health.router)
    app.include_router(dashboard.router)
    app.include_router(settings_api.router)
    app.include_router(repositories.router)
    app.include_router(investigations.router)
    app.include_router(reports.router)
    return app


app = create_app()
