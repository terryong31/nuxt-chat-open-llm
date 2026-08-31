from fastapi import APIRouter
from local_llm.models.manager import ModelManager

router = APIRouter(tags=["Health"])


@router.get("/")
def root():
    """Root server status and loaded models probe."""
    return {
        "status": "online",
        "active_model": ModelManager.model_id,
        "loaded_models": list(ModelManager._loaded_models.keys()),
        "docs_url": "/docs",
    }


@router.get("/health")
def health():
    """Healthcheck probe for deployment / monitoring."""
    return {"status": "healthy"}
