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
    ChatMessage,
    FunctionCall,
    ToolCallSpec,
)
from llm_engine.engine.base import (
    Completed,
    Delta,
    GenerationParams,
    Message,
    TextPart,
    ToolCall,
    ToolCalls,
    ToolSpec,
)

router = APIRouter(prefix="/chat", tags=["chat"])


def _to_messages(raw: list[ChatMessage]) -> list[Message]:
    """Convert wire messages to typed Message objects, tool turns included."""
    msgs: list[Message] = []
    for m in raw:
        content = m.content or ""
        tool_calls = tuple(
            ToolCall(
                id=tc.id,
                name=tc.function.name,
                arguments=_loads_or_empty(tc.function.arguments),
            )
            for tc in (m.tool_calls or [])
        )
        msgs.append(
            Message(
                role=m.role,
                content=(TextPart(content),),
                tool_calls=tool_calls,
                tool_call_id=m.tool_call_id,
            )
        )
    return msgs


def _loads_or_empty(raw: str) -> dict:
    try:
        value = json.loads(raw)
    except (ValueError, TypeError):
        return {}
    return value if isinstance(value, dict) else {}


def _to_tool_specs(body: ChatCompletionRequest) -> list[ToolSpec]:
    if body.tool_choice == "none" or not body.tools:
        return []
    return [
        ToolSpec(
            name=t.function.name,
            description=t.function.description,
            parameters=t.function.parameters,
        )
        for t in body.tools
    ]


def _to_wire_calls(calls: tuple[ToolCall, ...]) -> list[ToolCallSpec]:
    return [
        ToolCallSpec(
            id=c.id,
            function=FunctionCall(name=c.name, arguments=json.dumps(c.arguments)),
        )
        for c in calls
    ]


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
    messages = _to_messages(body.messages)
    tools = _to_tool_specs(body)

    if not body.stream:
        # Non-streaming completion
        response_text = ""
        tool_calls: list[ToolCallSpec] = []
        finish_reason = "stop"
        async for event in engine.stream_chat(messages, params, tools):
            if isinstance(event, Delta):
                response_text += event.text
            elif isinstance(event, ToolCalls):
                tool_calls = _to_wire_calls(event.calls)
            elif isinstance(event, Completed):
                finish_reason = event.finish_reason

        return ChatCompletionResponse(
            id=f"chatcmpl-{int(time.time())}",
            created=int(time.time()),
            model=body.model,
            choices=[
                ChatCompletionChoice(
                    index=0,
                    message=ChatCompletionChoiceMessage(
                        role="assistant",
                        # OpenAI sends null content, not "", alongside a call.
                        content=response_text or (None if tool_calls else ""),
                        tool_calls=tool_calls or None,
                    ),
                    finish_reason=finish_reason,
                )
            ],
        )

    # Streaming completion — SSE
    async def event_generator() -> AsyncGenerator[str]:
        created_ts = int(time.time())
        chat_id = f"chatcmpl-{created_ts}"

        def chunk(delta: dict, finish: str | None = None) -> str:
            data = {
                "id": chat_id,
                "object": "chat.completion.chunk",
                "created": created_ts,
                "model": body.model,
                "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
            }
            return f"data: {json.dumps(data)}\n\n"

        async for event in engine.stream_chat(messages, params, tools):
            if isinstance(event, Delta):
                yield chunk({"content": event.text})
            elif isinstance(event, ToolCalls):
                # Sent whole rather than as argument fragments: the engine only
                # knows the call once the JSON array is complete, and every
                # OpenAI client accepts a single fully-formed chunk.
                yield chunk(
                    {
                        "tool_calls": [
                            {
                                "index": i,
                                "id": c.id,
                                "type": "function",
                                "function": {
                                    "name": c.function.name,
                                    "arguments": c.function.arguments,
                                },
                            }
                            for i, c in enumerate(_to_wire_calls(event.calls))
                        ]
                    }
                )
            elif isinstance(event, Completed):
                yield chunk({}, event.finish_reason)

        yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
