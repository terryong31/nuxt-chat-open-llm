from fastapi import APIRouter
from local_llm.api.v1 import api_v1_router

# Central API Router aggregating v1 endpoints
api_router = APIRouter()
api_router.include_router(api_v1_router)

__all__ = ["api_router"]
