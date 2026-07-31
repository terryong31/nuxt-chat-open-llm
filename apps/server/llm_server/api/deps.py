"""Dependencies wired into routes.

Routes ask for what they need instead of importing module globals. That is what
makes them testable: `app.dependency_overrides[get_chat_service] = fake` swaps
the whole stack without loading a checkpoint.
"""

from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ..config import Settings
from ..engine.base import LLMEngine
from ..services.chat import ChatService


def get_settings(request: Request) -> Settings:
    """Read settings off the app, not the cached module-level singleton.

    The factory accepts a `Settings` argument, so resolving it from the env
    here instead would silently ignore whatever was passed to `create_app` --
    which is exactly how a test that thinks it enabled auth ends up asserting
    against a server that never did.
    """
    return request.app.state.settings


SettingsDep = Annotated[Settings, Depends(get_settings)]

# auto_error=False so a missing header reaches our own check, which knows
# whether auth is switched on at all.
_bearer = HTTPBearer(auto_error=False, description="OpenAI-style API key")


def get_engine(request: Request) -> LLMEngine:
    """The engine built by the app factory and started by the lifespan."""
    return request.app.state.engine


EngineDep = Annotated[LLMEngine, Depends(get_engine)]


def get_chat_service(engine: EngineDep, settings: SettingsDep) -> ChatService:
    return ChatService(engine=engine, settings=settings)


ChatServiceDep = Annotated[ChatService, Depends(get_chat_service)]


def require_api_key(
    settings: SettingsDep,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(_bearer)
    ] = None,
) -> None:
    """No-op until `LLM_API_KEYS` is set.

    Attached to the /v1 router now so that turning auth on is configuration
    rather than a code change -- and so nothing can be added to that router
    later that quietly bypasses it.
    """
    if not settings.api_keys:
        return

    presented = credentials.credentials if credentials else ""
    # compare_digest against every key: short-circuiting on the first match
    # would leak which prefix was right through response timing.
    if not any(secrets.compare_digest(presented, key) for key in settings.api_keys):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or missing API key",
            headers={"WWW-Authenticate": "Bearer"},
        )
