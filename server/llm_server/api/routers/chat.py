"""POST /v1/chat/completions -- streaming and buffered."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from ...engine.base import Completed, Delta, StreamEvent
from ...services.chat import ChatOptions
from .. import schemas
from ..deps import ChatServiceDep

log = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])

# Proxies love to buffer text/event-stream into uselessness. These headers ask
# nginx and friends to pass bytes through as they arrive.
_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


@dataclass(frozen=True, slots=True)
class _Envelope:
    """The identity every frame of one response shares."""

    id: str
    created: int
    model: str


@router.post("/chat/completions")
async def create_chat_completion(
    payload: schemas.ChatCompletionRequest,
    chat: ChatServiceDep,
):
    stream = chat.stream(payload.to_domain(), _options(payload))

    # Pull the first event before deciding on a response. Admission control and
    # "model not loaded" have to surface as real status codes, and a
    # StreamingResponse commits to its status the moment headers go out -- an
    # error raised after that can only be reported inside the body, where
    # clients handle it badly. `stream` is an async generator, so nothing has
    # run until this line.
    first = await anext(stream, None)

    envelope = _Envelope(
        id=schemas.new_completion_id(),
        created=schemas.now(),
        model=chat.model_id,
    )

    if payload.stream:
        return StreamingResponse(
            _sse(stream, first, envelope),
            media_type="text/event-stream",
            headers=_SSE_HEADERS,
        )
    return await _buffered(stream, first, envelope)


def _options(payload: schemas.ChatCompletionRequest) -> ChatOptions:
    return ChatOptions(
        max_tokens=payload.max_tokens,
        temperature=payload.temperature,
        top_p=payload.top_p,
    )


def _frame(
    envelope: _Envelope,
    delta: schemas.ChunkDelta,
    finish_reason: str | None = None,
    usage: schemas.Usage | None = None,
) -> str:
    """One SSE frame. `exclude_none` keeps chunks close to OpenAI's on the wire."""
    chunk = schemas.ChatCompletionChunk(
        id=envelope.id,
        created=envelope.created,
        model=envelope.model,
        choices=[schemas.ChunkChoice(delta=delta, finish_reason=finish_reason)],
        usage=usage,
    )
    return f"data: {chunk.model_dump_json(exclude_none=True)}\n\n"


async def _sse(
    stream: AsyncIterator[StreamEvent],
    first: StreamEvent | None,
    envelope: _Envelope,
) -> AsyncIterator[str]:
    # OpenAI's first chunk announces the role and carries no text; clients that
    # build up a message object rely on seeing it.
    yield _frame(envelope, schemas.ChunkDelta(role="assistant"))

    try:
        event = first
        while event is not None:
            if isinstance(event, Delta):
                yield _frame(envelope, schemas.ChunkDelta(content=event.text))
            elif isinstance(event, Completed):
                yield _frame(
                    envelope,
                    schemas.ChunkDelta(),
                    finish_reason=event.finish_reason,
                    usage=schemas.Usage.from_domain(event.usage),
                )
            event = await anext(stream, None)
    except Exception as exc:  # noqa: BLE001
        # The status line left the building several chunks ago. An explicit
        # error frame before the terminator is the only honest signal left --
        # otherwise a truncated answer is indistinguishable from a short one.
        log.exception("generation failed mid-stream")
        error = schemas.ErrorResponse(
            error=schemas.ErrorBody(
                message=str(exc), type=getattr(exc, "type", "internal_error")
            )
        )
        yield f"data: {error.model_dump_json()}\n\n"
    else:
        yield "data: [DONE]\n\n"
    finally:
        # Awaiting is safe while this generator is being closed on a client
        # disconnect; yielding would not be, which is why [DONE] lives in the
        # `else` branch rather than here.
        await stream.aclose()


async def _buffered(
    stream: AsyncIterator[StreamEvent],
    first: StreamEvent | None,
    envelope: _Envelope,
) -> schemas.ChatCompletion:
    parts: list[str] = []
    finish_reason = "stop"
    usage = schemas.Usage(prompt_tokens=0, completion_tokens=0, total_tokens=0)

    try:
        event = first
        while event is not None:
            if isinstance(event, Delta):
                parts.append(event.text)
            elif isinstance(event, Completed):
                finish_reason = event.finish_reason
                usage = schemas.Usage.from_domain(event.usage)
            event = await anext(stream, None)
    finally:
        await stream.aclose()

    return schemas.ChatCompletion(
        id=envelope.id,
        created=envelope.created,
        model=envelope.model,
        choices=[
            schemas.Choice(
                message=schemas.ResponseMessage(content="".join(parts)),
                finish_reason=finish_reason,
            )
        ],
        usage=usage,
    )
