from fastapi import APIRouter
from local_llm.api.v1.endpoints.chat import router as chat_router
from local_llm.api.v1.endpoints.health import router as health_router

api_v1_router = APIRouter()
api_v1_router.include_router(chat_router)
api_v1_router.include_router(health_router)

__all__ = ["api_v1_router"]
