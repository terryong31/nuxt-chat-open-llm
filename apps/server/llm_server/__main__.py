"""Entrypoint.

    uv run llm-server        # from anywhere in the repo
    python -m llm_server     # same, without uv

All the wiring lives in `llm_server.app`; this file only chooses how to serve it.
"""

import uvicorn

from llm_server.asgi import app
from llm_server.config import get_settings


def main() -> None:
    settings = get_settings()
    # The app object is passed directly rather than as an import string, which
    # rules out the two options that would each load a second copy of the model:
    # reload=True forks a reloader that re-imports this module, and workers > 1
    # gives every worker its own multi-GB set of weights. One process, one copy.
    # Scale by putting more machines behind a proxy, not more workers in front
    # of one GPU.
    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
