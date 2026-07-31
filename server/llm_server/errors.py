"""Domain errors, raised by the engine and service layers.

These deliberately carry no HTTP vocabulary -- `app.py` owns the mapping from
these to status codes. That is what lets the engine and service layers be used
from a CLI, a worker, or a test without dragging FastAPI along.
"""


class LLMError(RuntimeError):
    """Base class for every failure this server knows how to describe."""

    # OpenAI's error envelope has a machine-readable `type`; clients switch on
    # it, so each subclass names its own.
    type: str = "internal_error"


class EngineNotReady(LLMError):
    """Weights are not resident yet, or failed to load."""

    type = "engine_not_ready"


class EngineBusy(LLMError):
    """Admission control rejected the request. Retrying later will work."""

    type = "engine_busy"


class UnsupportedContent(LLMError):
    """The request is well-formed but this engine cannot serve it.

    Raised for e.g. image parts sent to a text-only checkpoint. Distinct from a
    validation error: the wire format is valid, the *engine* is the limitation.
    """

    type = "unsupported_content"


class GenerationFailed(LLMError):
    """The model runtime raised while generating."""

    type = "generation_failed"
