from typing import Annotated

from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from llm_engine.config import get_settings

security = HTTPBearer(auto_error=False)
SecurityCredentials = Annotated[HTTPAuthorizationCredentials | None, Security(security)]


async def require_api_key(
    credentials: SecurityCredentials = None,
) -> None:
    settings = get_settings()
    if not settings.api_keys:
        return
    if not credentials or credentials.credentials not in settings.api_keys:
        raise HTTPException(status_code=401, detail="Invalid API Key")
