"""Wire contracts, shaped after the OpenAI chat-completions API.

Being bug-compatible with OpenAI is worth more than a tidier bespoke schema:
`openai-python`, the Vercel AI SDK, and most chat UIs already speak it, so the
Nuxt app can use an off-the-shelf client with a changed `baseURL`, and swapping
this server for a hosted model later touches no frontend code.

Only the subset that means something here is implemented. Unknown fields are
ignored rather than rejected, because real clients send `n`, `presence_penalty`
and friends unconditionally and a 422 would be unhelpful.
"""

from __future__ import annotations

import time
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ..engine.base import ContentPart, ImagePart, Message, Role, TextPart
from ..engine.base import Usage as DomainUsage


def new_completion_id() -> str:
    """Every frame of one streamed response repeats this id, so routes mint it
    once up front rather than letting each chunk default its own."""
    return f"chatcmpl-{uuid.uuid4().hex}"


def now() -> int:
    return int(time.time())


# -- request ----------------------------------------------------------------


class TextContent(BaseModel):
    type: Literal["text"]
    text: str


class ImageURL(BaseModel):
    url: str
    detail: Literal["auto", "low", "high"] = "auto"


class ImageContent(BaseModel):
    type: Literal["image_url"]
    image_url: ImageURL


ContentItem = TextContent | ImageContent


class ChatMessage(BaseModel):
    role: Role
    # OpenAI allows either a bare string or an array of typed parts. Both are
    # accepted; both normalise to parts before leaving this layer.
    content: str | list[ContentItem]

    def to_domain(self) -> Message:
        if isinstance(self.content, str):
            return Message.text(self.role, self.content)

        parts: list[ContentPart] = []
        for item in self.content:
            if isinstance(item, TextContent):
                parts.append(TextPart(item.text))
            else:
                parts.append(
                    ImagePart(url=item.image_url.url, detail=item.image_url.detail)
                )
        return Message(role=self.role, content=tuple(parts))


class ChatCompletionRequest(BaseModel):
    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    messages: list[ChatMessage] = Field(min_length=1)
    # Accepted and echoed back. This server hosts exactly one checkpoint, so
    # the value is not used for routing -- but clients always send it.
    model: str | None = None
    stream: bool = False
    # `None` defers to the server default. The upper bound is enforced in the
    # service layer, where the settings live.
    max_tokens: int | None = Field(default=None, ge=1)
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    top_p: float | None = Field(default=None, gt=0.0, le=1.0)

    def to_domain(self) -> list[Message]:
        return [m.to_domain() for m in self.messages]


# -- response ---------------------------------------------------------------


class Usage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int

    @classmethod
    def from_domain(cls, usage: DomainUsage) -> Usage:
        return cls(
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            total_tokens=usage.total_tokens,
        )


class ResponseMessage(BaseModel):
    role: Literal["assistant"] = "assistant"
    content: str


class Choice(BaseModel):
    index: int = 0
    message: ResponseMessage
    finish_reason: str


class ChatCompletion(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    id: str = Field(default_factory=new_completion_id)
    object: Literal["chat.completion"] = "chat.completion"
    created: int = Field(default_factory=now)
    model: str
    choices: list[Choice]
    usage: Usage


class ChunkDelta(BaseModel):
    role: Literal["assistant"] | None = None
    content: str | None = None


class ChunkChoice(BaseModel):
    index: int = 0
    delta: ChunkDelta
    finish_reason: str | None = None


class ChatCompletionChunk(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    id: str
    object: Literal["chat.completion.chunk"] = "chat.completion.chunk"
    created: int
    model: str
    choices: list[ChunkChoice]
    # Only the terminal chunk carries usage, matching `stream_options`.
    usage: Usage | None = None


# -- models listing ---------------------------------------------------------


class ModelCard(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    id: str
    object: Literal["model"] = "model"
    created: int = Field(default_factory=now)
    owned_by: str = "local"


class ModelList(BaseModel):
    object: Literal["list"] = "list"
    data: list[ModelCard]


# -- errors -----------------------------------------------------------------


class ErrorBody(BaseModel):
    message: str
    type: str
    code: str | None = None


class ErrorResponse(BaseModel):
    """OpenAI nests errors under an `error` key; clients unwrap that shape."""

    error: ErrorBody
