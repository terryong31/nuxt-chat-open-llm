"""The ASGI object, for process managers that want an import string.

    uvicorn llm_server.asgi:app

Only the app is built here -- the weights load in the lifespan handler, once,
in the serving process. Never at module import.

Prefer `llm-server` over this. An import string is what makes `--workers N`
possible, and N copies of a 3.8 GB model on one GPU is never what you want.
"""

from llm_server.app import create_app

app = create_app()
