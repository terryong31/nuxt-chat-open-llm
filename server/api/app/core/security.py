import logging
from typing import Annotated

import jwt
from app.core.config import get_settings
from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

logger = logging.getLogger(__name__)
security = HTTPBearer(auto_error=False)
SecurityCredentials = Annotated[HTTPAuthorizationCredentials | None, Security(security)]

DEV_USER = {
    "id": "4f533119-0832-497f-9c0d-22bc78017e3f",
    "email": "dev@local.host",
    "user_metadata": {"preferred_username": "devuser"},
}


async def get_current_user(
    credentials: SecurityCredentials = None,
) -> dict:
    """FastAPI dependency for Supabase JWT verification.

    - DEV mode (`APP_ENV=development`): Skips strict auth checks.
    - STG & PROD modes (`staging`, `production`): Strictly requires valid JWT token.
    """
    settings = get_settings()

    # 1. DEVELOPMENT MODE: Skip strict auth check
    if settings.app_env == "development":
        if not credentials or not credentials.credentials:
            return DEV_USER
        try:
            payload = jwt.decode(
                credentials.credentials, options={"verify_signature": False}
            )
            user_id = payload.get("sub", DEV_USER["id"])
            return {
                "id": user_id,
                "email": payload.get("email"),
                "user_metadata": payload.get("user_metadata", {}),
            }
        except Exception:  # noqa: BLE001
            return DEV_USER

    # 2. STAGING & PRODUCTION MODES: Strict authentication required
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=401, detail="Missing Bearer Authorization Token"
        )

    if not settings.supabase_jwt_secret:
        raise HTTPException(
            status_code=500,
            detail="Server authentication misconfigured: missing SUPABASE_JWT_SECRET",
        )

    token = credentials.credentials
    try:
        payload = jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            options={"verify_aud": False},
        )
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=401, detail="Invalid token claims: missing sub"
            )
        return {
            "id": user_id,
            "email": payload.get("email"),
            "user_metadata": payload.get("user_metadata", {}),
        }
    except jwt.PyJWTError as e:
        raise HTTPException(
            status_code=401, detail=f"Invalid authorization token: {e!s}"
        ) from e
