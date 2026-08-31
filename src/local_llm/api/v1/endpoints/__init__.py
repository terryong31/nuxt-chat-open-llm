from local_llm.api.v1.endpoints.chat import router as chat_router
from local_llm.api.v1.endpoints.health import router as health_router

__all__ = ["chat_router", "health_router"]
