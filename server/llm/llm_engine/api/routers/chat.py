import json
import time
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from llm_engine.api.schemas import (
    ChatCompletionChoice,
    ChatCompletionChoiceMessage,
    ChatCompletionRequest,
    ChatCompletionResponse,
)
from llm_engine.engine.base import Completed, Delta, GenerationParams, Message

router = APIRouter(prefix="/chat", tags=["chat"])


def _to_messages(raw: list[dict]) -> list[Message]:
    """Convert OpenAI-style dicts to typed Message objects."""
    msgs = []
    for m in raw:
        role = m.get("role", "user")
        content = m.get("content", "")
        if isinstance(content, list):
            # Multipart content — join text parts
            content = " ".join(
                p.get("text", "") for p in content if p.get("type") == "text"
            )
        msgs.append(Message.text(role, content))
    return msgs


@router.post("/completions")
async def chat_completions(request: Request, body: ChatCompletionRequest):
    engine = request.app.state.engine
    settings = request.app.state.settings

    params = GenerationParams(
        max_tokens=body.resolved_max_tokens or settings.default_max_tokens,
        temperature=body.temperature
        if body.temperature is not None
        else settings.temperature,
        top_p=body.top_p if body.top_p is not None else settings.top_p,
        repetition_penalty=settings.repetition_penalty,
        repetition_context_size=settings.repetition_context_size,
    )
    messages = _to_messages(
        [{"role": m.role, "content": m.content} for m in body.messages]
    )

    if not body.stream:
        # Non-streaming completion
        response_text = ""
        async for event in engine.stream_chat(messages, params):
            if isinstance(event, Delta):
                response_text += event.text

        return ChatCompletionResponse(
            id=f"chatcmpl-{int(time.time())}",
            created=int(time.time()),
            model=body.model,
            choices=[
                ChatCompletionChoice(
                    index=0,
                    message=ChatCompletionChoiceMessage(
                        role="assistant", content=response_text
                    ),
                    finish_reason="stop",
                )
            ],
        )

    # Streaming completion — SSE
    async def event_generator() -> AsyncGenerator[str]:
        created_ts = int(time.time())
        chat_id = f"chatcmpl-{created_ts}"

        async for event in engine.stream_chat(messages, params):
            if isinstance(event, Delta):
                data = {
                    "id": chat_id,
                    "object": "chat.completion.chunk",
                    "created": created_ts,
                    "model": body.model,
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"content": event.text},
                            "finish_reason": None,
                        }
                    ],
                }
                yield f"data: {json.dumps(data)}\n\n"
            elif isinstance(event, Completed):
                final_data = {
                    "id": chat_id,
                    "object": "chat.completion.chunk",
                    "created": created_ts,
                    "model": body.model,
                    "choices": [
                        {"index": 0, "delta": {}, "finish_reason": event.finish_reason}
                    ],
                }
                yield f"data: {json.dumps(final_data)}\n\n"

        yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
