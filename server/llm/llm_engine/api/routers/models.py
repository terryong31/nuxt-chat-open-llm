from fastapi import APIRouter

from llm_engine.config import get_settings

router = APIRouter(prefix="/models", tags=["models"])


@router.get("")
async def list_models():
    settings = get_settings()
    return {
        "object": "list",
        "data": [
            {
                "id": settings.model_id,
                "object": "model",
                "created": 1700000000,
                "owned_by": "local",
            }
        ],
    }
