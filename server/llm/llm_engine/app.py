from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import __version__
from .api import schemas
from .api.deps import require_api_key
from .api.routers import chat, health, models
from .config import Settings, get_settings
from .engine.base import LLMEngine
from .engine.mlx_engine import MlxEngine
from .errors import EngineBusy, EngineNotReady, LLMError, UnsupportedContent
from .observability import RequestContextMiddleware, configure_logging

_STATUS_BY_ERROR: tuple[tuple[type[LLMError], int], ...] = (
    (EngineBusy, 503),
    (EngineNotReady, 503),
    (UnsupportedContent, 400),
)
_DEFAULT_ERROR_STATUS = 500


def create_app(
    settings: Settings | None = None,
    engine: LLMEngine | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await app.state.engine.start()
        try:
            yield
        finally:
            await app.state.engine.stop()

    app = FastAPI(
        title="LLM Inference Engine Microservice",
        version=__version__,
        summary="OpenAI-compatible inference microservice.",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.engine = engine if engine is not None else MlxEngine(settings)

    _add_middleware(app, settings)
    _add_error_handlers(app)
    _add_routes(app)
    return app


def _add_middleware(app: FastAPI, settings: Settings) -> None:
    app.add_middleware(RequestContextMiddleware)
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["*"],
            expose_headers=["x-request-id"],
        )


def _add_routes(app: FastAPI) -> None:
    v1 = APIRouter(prefix="/v1", dependencies=[Depends(require_api_key)])
    v1.include_router(chat.router)
    v1.include_router(models.router)
    app.include_router(v1)
    app.include_router(health.router)


def _add_error_handlers(app: FastAPI) -> None:
    def _envelope(message: str, error_type: str, status_code: int, headers=None):
        body = schemas.ErrorResponse(
            error=schemas.ErrorBody(message=message, type=error_type)
        )
        return JSONResponse(
            status_code=status_code, content=body.model_dump(), headers=headers
        )

    @app.exception_handler(LLMError)
    async def _on_llm_error(_: Request, exc: LLMError) -> JSONResponse:
        status_code = next(
            (code for cls, code in _STATUS_BY_ERROR if isinstance(exc, cls)),
            _DEFAULT_ERROR_STATUS,
        )
        headers = {"Retry-After": "5"} if status_code == 503 else None
        return _envelope(str(exc), exc.type, status_code, headers)

    @app.exception_handler(HTTPException)
    async def _on_http_error(_: Request, exc: HTTPException) -> JSONResponse:
        return _envelope(
            str(exc.detail), "invalid_request_error", exc.status_code, exc.headers
        )
