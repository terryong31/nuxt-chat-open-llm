from typing import Annotated

from app.core.security import get_current_user
from app.services.llm_client import LLMClient
from fastapi import APIRouter, Depends

router = APIRouter(prefix="/v1/models", tags=["models"])
CurrentUser = Annotated[dict, Depends(get_current_user)]


@router.get("")
async def list_models(current_user: CurrentUser):
    """Model ids the engine has loaded, for the UI's picker.

    Proxied rather than configured here so the picker cannot drift from what is
    actually served. A hardcoded list is how it came to advertise three hosted
    models that every request quietly answered with the local checkpoint.
    """
    return {"data": [{"id": model_id} for model_id in await LLMClient.list_models()]}
