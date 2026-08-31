from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers.chat import router as chat_router, ModelManager
import uvicorn
import os
from dotenv import load_dotenv

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Startup: Preload all models into Unified Memory
    ModelManager.preload_all_models()
    yield
    # 2. Shutdown (Ctrl+C / KeyboardInterrupt): Flush all models from Unified Memory
    print("\n🛑 Shutting down local LLM server...")
    ModelManager.unload_all()


app = FastAPI(
    title="Local MLX LLM API",
    description="High-performance Apple Silicon Local LLM API using FastAPI & MLX",
    version="1.0.0",
    lifespan=lifespan,
)

# Enable CORS for Nuxt / Vue web frontend (e.g. localhost:3000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(chat_router)


@app.get("/")
def root():
    return {
        "status": "online",
        "active_model": ModelManager.model_id,
        "loaded_models": list(ModelManager._loaded_models.keys()),
        "docs_url": "/docs",
    }


@app.get("/health")
def health():
    return {"status": "healthy"}


if __name__ == "__main__":
    should_reload = os.getenv("RELOAD", "false").lower() in ("true", "1")
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=should_reload,
        reload_dirs=["routers", "agent", "tools"] if should_reload else None,
        reload_includes=["*.py"] if should_reload else None,
    )