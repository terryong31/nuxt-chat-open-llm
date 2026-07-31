"""GET /v1/models.

Not decoration: OpenAI-compatible clients probe this to validate a base URL and
to populate model pickers, and several fail closed without it.
"""

from fastapi import APIRouter

from .. import schemas
from ..deps import EngineDep

router = APIRouter(tags=["models"])


@router.get("/models", response_model=schemas.ModelList)
def list_models(engine: EngineDep) -> schemas.ModelList:
    return schemas.ModelList(data=[schemas.ModelCard(id=engine.model_id)])
