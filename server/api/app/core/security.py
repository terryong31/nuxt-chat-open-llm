from typing import Annotated

import jwt
from app.core.config import get_settings
from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

security = HTTPBearer(auto_error=False)
SecurityCredentials = Annotated[HTTPAuthorizationCredentials | None, Security(security)]


async def get_current_user(
    credentials: SecurityCredentials = None,
) -> dict:
    """FastAPI dependency to validate incoming Supabase Bearer JWT.

    Decodes token claims locally using LLM_SUPABASE_JWT_SECRET or allows unauthenticated
    development mode if JWT secret is not configured.
    """
    settings = get_settings()

    if not credentials:
        if not settings.supabase_jwt_secret:
            return {
                "id": "00000000-0000-0000-0000-000000000000",
                "email": "dev@local.host",
            }
        raise HTTPException(
            status_code=401, detail="Missing Bearer Authorization Token"
        )

    token = credentials.credentials

    if not settings.supabase_jwt_secret:
        try:
            payload = jwt.decode(token, options={"verify_signature": False})
            user_id = payload.get("sub", "00000000-0000-0000-0000-000000000000")
            return {
                "id": user_id,
                "email": payload.get("email"),
                "user_metadata": payload.get("user_metadata", {}),
            }
        except jwt.PyJWTError:
            return {
                "id": "00000000-0000-0000-0000-000000000000",
                "email": "dev@local.host",
            }

    try:
        payload = jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            audience="authenticated",
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
