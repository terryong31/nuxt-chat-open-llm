"""Operational endpoints.

Split into liveness and readiness on purpose. Conflating them is how a slow
model load turns into a restart loop: an orchestrator that health-checks the
wrong one kills the process for being slow, and the replacement is just as slow.
"""

from fastapi import APIRouter, Response, status

from ..deps import EngineDep

router = APIRouter(tags=["ops"])


@router.get("/healthz", summary="Liveness")
def liveness() -> dict[str, str]:
    """Says only that the process is running.

    Deliberately reports nothing about the model: restarting would not make a
    load any faster, so this must keep returning 200 during warm-up.
    """
    return {"status": "ok"}


@router.get("/readyz", summary="Readiness")
def readiness(engine: EngineDep, response: Response) -> dict[str, object]:
    """Says whether traffic can actually be served.

    Returns 503 until the weights are resident, which is the signal a load
    balancer or `docker compose --wait` should gate on.
    """
    if not engine.is_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "ready": engine.is_ready,
        "model": engine.model_id,
        "memory": engine.stats(),
    }
