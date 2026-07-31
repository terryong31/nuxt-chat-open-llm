"""Chat orchestration.

Today this is close to a passthrough to the engine, and that is fine -- its
value is positional. Everything that is *about the conversation* rather than
about HTTP or about tensors belongs here: policy on sampling defaults, refusing
content the engine cannot serve, and later retrieval, tool calls, or a
LangGraph agent.

When that arrives, `stream` grows a graph invocation and starts yielding tool
events alongside text. Routes keep consuming the same event stream and the
engine keeps knowing nothing about any of it.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass

from ..config import Settings
from ..engine.base import GenerationParams, LLMEngine, Message, StreamEvent
from ..errors import UnsupportedContent


@dataclass(frozen=True, slots=True)
class ChatOptions:
    """Per-request sampling overrides. `None` means "use the server default"."""

    max_tokens: int | None = None
    temperature: float | None = None
    top_p: float | None = None


class ChatService:
    def __init__(self, engine: LLMEngine, settings: Settings) -> None:
        self._engine = engine
        self._settings = settings

    @property
    def model_id(self) -> str:
        """Echoed back on responses. Routes should not reach past the service
        to the engine just to name the model that answered."""
        return self._engine.model_id

    def stream(
        self,
        messages: Sequence[Message],
        options: ChatOptions,
    ) -> AsyncIterator[StreamEvent]:
        """Stream a reply. Nothing runs until the first `__anext__`."""
        self._reject_unsupported(messages)
        return self._engine.stream_chat(messages, self._resolve(options))

    def _reject_unsupported(self, messages: Sequence[Message]) -> None:
        if self._engine.supports_images:
            return
        if any(m.has_images for m in messages):
            raise UnsupportedContent(
                f"{self._engine.model_id} is a text-only model and cannot "
                "accept image content"
            )

    def _resolve(self, options: ChatOptions) -> GenerationParams:
        s = self._settings
        requested = options.max_tokens or s.default_max_tokens
        return GenerationParams(
            # Clamped rather than rejected: a client asking for more tokens than
            # this box will serve should get a shorter answer, not an error. The
            # ceiling is what stops one request monopolising the GPU.
            max_tokens=min(requested, s.max_tokens_limit),
            temperature=(
                options.temperature
                if options.temperature is not None
                else s.temperature
            ),
            top_p=options.top_p if options.top_p is not None else s.top_p,
            repetition_penalty=s.repetition_penalty,
            repetition_context_size=s.repetition_context_size,
        )
