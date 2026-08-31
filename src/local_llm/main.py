from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from local_llm.core.config import settings
from local_llm.models.manager import ModelManager
from local_llm.api.router import api_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI Lifespan Context Manager.
    - Startup: Preloads all configured models into Unified Memory.
    - Shutdown: Cleans all models and clears Metal cache on Ctrl+C / SIGINT.
    """
    # 1. Startup: Preload all models into Unified Memory
    ModelManager.preload_all_models()
    yield
    # 2. Shutdown (Ctrl+C / KeyboardInterrupt): Flush all models from Unified Memory
    print("\n🛑 Shutting down local LLM server...")
    ModelManager.unload_all()


def create_app() -> FastAPI:
    """
    FastAPI Application Factory.
    """
    app = FastAPI(
        title=settings.PROJECT_NAME,
        description=settings.PROJECT_DESCRIPTION,
        version=settings.VERSION,
        lifespan=lifespan,
    )

    # Enable CORS for Nuxt / Vue frontend
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register central API routers
    app.include_router(api_router)

    return app


app = create_app()


def main():
    """CLI Entrypoint."""
    uvicorn.run(
        "local_llm.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.RELOAD,
    )


if __name__ == "__main__":
    main()
