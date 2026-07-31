"""Application factory and wiring.

`create_app` takes both collaborators as arguments so a test can pass a fake
engine and never load a checkpoint. This is also the one file that knows the
concrete engine class -- pointing the server at vLLM or a remote endpoint means
changing the default here and nothing else.
"""

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

# Every domain error maps to exactly one status code, in one place, rather than
# each route inventing its own.
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
        # Weights load once, here -- never at module import, which would give
        # every process that imports this file its own multi-GB copy.
        await app.state.engine.start()
        try:
            yield
        finally:
            await app.state.engine.stop()

    app = FastAPI(
        title="Local LLM",
        version=__version__,
        summary="OpenAI-compatible inference for a locally hosted model.",
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
            # Without this the browser can see the header but JS cannot read
            # it, which makes correlating a frontend bug to a server log hard.
            expose_headers=["x-request-id"],
        )


def _add_routes(app: FastAPI) -> None:
    # The dependency sits on the router, not on each route, so a handler added
    # here later cannot accidentally skip auth.
    v1 = APIRouter(prefix="/v1", dependencies=[Depends(require_api_key)])
    v1.include_router(chat.router)
    v1.include_router(models.router)
    app.include_router(v1)

    # Probes stay unauthenticated: an orchestrator should not need a key to
    # find out whether the process is alive.
    app.include_router(health.router)


def _add_error_handlers(app: FastAPI) -> None:
    def _envelope(message: str, error_type: str, status_code: int, headers=None):
        body = schemas.ErrorResponse(
            error=schemas.ErrorBody(message=message, type=error_type)
        )
        return JSONResponse(
            status_code=status_code, content=body.model_dump(), headers=headers
        )

    # Starlette resolves handlers by walking the exception's MRO, so
    # registering the base class covers every subclass.
    @app.exception_handler(LLMError)
    async def _on_llm_error(_: Request, exc: LLMError) -> JSONResponse:
        status_code = next(
            (code for cls, code in _STATUS_BY_ERROR if isinstance(exc, cls)),
            _DEFAULT_ERROR_STATUS,
        )
        # Tell a client that hit admission control when to come back, instead
        # of leaving it to guess and hammer.
        headers = {"Retry-After": "5"} if status_code == 503 else None
        return _envelope(str(exc), exc.type, status_code, headers)

    @app.exception_handler(HTTPException)
    async def _on_http_error(_: Request, exc: HTTPException) -> JSONResponse:
        # Restated in OpenAI's envelope so clients only ever parse one error
        # shape, whether it came from auth or from the engine.
        return _envelope(
            str(exc.detail), "invalid_request_error", exc.status_code, exc.headers
        )
