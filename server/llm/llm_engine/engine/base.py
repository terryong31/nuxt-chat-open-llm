"""The contract between the HTTP layer and a model runtime.

Nothing here imports mlx or fastapi, and that is the point. Routes depend on
`LLMEngine`, so replacing the in-process MLX runtime with a remote vLLM or
Ollama backend is a new implementation of this protocol plus one line in
`app.py` -- not a rewrite. Tests get a fake engine for free.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

Role = Literal["system", "user", "assistant", "tool"]
FinishReason = Literal["stop", "length", "tool_calls"]


@dataclass(frozen=True, slots=True)
class TextPart:
    text: str


@dataclass(frozen=True, slots=True)
class ImagePart:
    """An image reference: either an http(s) URL or a `data:` URI.

    No engine here can serve one yet. It exists so that adding a vision model
    is a new `LLMEngine` implementation rather than a breaking change to the
    wire format and every layer in between.
    """

    url: str
    detail: Literal["auto", "low", "high"] = "auto"


ContentPart = TextPart | ImagePart


@dataclass(frozen=True, slots=True)
class ToolCall:
    """A tool the model asked to run. This engine never runs one.

    Executing tools is the gateway's job — the engine only reports intent, which
    is what keeps the agent loop out of the single generation slot
    (ADR 0006, ADR 0007).
    """

    id: str
    name: str
    arguments: dict


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """A tool offered to the model, framework-agnostic.

    Deliberately not OpenAI's `{"type": "function", "function": {...}}` envelope:
    the wire shape belongs to the API layer, and `prompts.py` rebuilds whichever
    form a given checkpoint was trained on.
    """

    name: str
    description: str
    parameters: dict


@dataclass(frozen=True, slots=True)
class Message:
    """One turn. Content is a sequence of parts, mirroring the OpenAI schema.

    Plain-string content on the wire is normalised to a single `TextPart`, so
    downstream code only ever handles one shape.
    """

    role: Role
    content: tuple[ContentPart, ...]
    # Set on an assistant turn that asked for tools, and on the `tool` turn
    # carrying the result back. Both are needed to replay a tool exchange into
    # the prompt on the follow-up request.
    tool_calls: tuple[ToolCall, ...] = ()
    tool_call_id: str | None = None

    @classmethod
    def text(cls, role: Role, text: str) -> Message:
        return cls(role=role, content=(TextPart(text),))

    @property
    def as_text(self) -> str:
        """The text parts joined. Non-text parts are dropped, so callers that
        use this must first check the engine actually supports them."""
        return "".join(p.text for p in self.content if isinstance(p, TextPart))

    @property
    def has_images(self) -> bool:
        return any(isinstance(p, ImagePart) for p in self.content)


@dataclass(frozen=True, slots=True)
class GenerationParams:
    max_tokens: int
    temperature: float
    top_p: float
    repetition_penalty: float
    repetition_context_size: int


@dataclass(frozen=True, slots=True)
class Usage:
    prompt_tokens: int
    completion_tokens: int

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@dataclass(frozen=True, slots=True)
class Delta:
    """One incremental piece of assistant text."""

    text: str


@dataclass(frozen=True, slots=True)
class ToolCalls:
    """The model asked for tools. Emitted once, just before `Completed`.

    Not streamed incrementally: the call only means anything as complete JSON,
    and a half-parsed one would be worse than waiting for the whole array.
    """

    calls: tuple[ToolCall, ...]


@dataclass(frozen=True, slots=True)
class Completed:
    """Terminal event. Always the last item of a stream that ran to completion."""

    finish_reason: FinishReason
    usage: Usage


StreamEvent = Delta | ToolCalls | Completed


@runtime_checkable
class LLMEngine(Protocol):
    """A model runtime that can stream a chat completion.

    `stream_chat` is an async *generator* function: calling it returns an
    iterator without doing any work, and the first `__anext__` is what acquires
    a generation slot. Callers rely on that -- see the note in the chat route
    about pulling the first event before the response headers go out.
    """

    model_id: str
    supports_images: bool
    supports_tools: bool

    @property
    def is_ready(self) -> bool: ...

    async def start(self) -> None: ...

    async def stop(self) -> None: ...

    def stats(self) -> dict[str, float]: ...

    def stream_chat(
        self,
        messages: Sequence[Message],
        params: GenerationParams,
        tools: Sequence[ToolSpec] = (),
    ) -> AsyncIterator[StreamEvent]: ...
