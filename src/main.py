import uvicorn
from local_llm.core.config import settings

if __name__ == "__main__":
    uvicorn.run(
        "local_llm.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.RELOAD,
        reload_dirs=["local_llm"] if settings.RELOAD else None,
    )