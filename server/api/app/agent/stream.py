"""AI SDK UI Message Stream adapter for LangGraph astream_events.

The Vercel AI SDK v5+ `useChat` hook (`ai@7`, `@ai-sdk/vue@4`) consumes **SSE**,
not the old `0:"token"` data-stream protocol that v3/v4 spoke. Each SSE frame
carries one JSON chunk object:

  data: {"type":"start"}
  data: {"type":"start-step"}
  data: {"type":"text-start","id":"..."}
  data: {"type":"text-delta","id":"...","delta":"Hello"}
  data: {"type":"text-end","id":"..."}
  data: {"type":"finish-step"}
  data: {"type":"finish"}
  data: [DONE]

A `text-delta` whose `id` was never opened by a `text-start` is dropped with a
console warning, which is why the text part is opened lazily but always closed.

Reference: https://ai-sdk.dev/docs/ai-sdk-ui/stream-protocol#ui-message-stream
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

logger = logging.getLogger(__name__)

DONE = "data: [DONE]\n\n"

# The title runs on the same model as the reply, so its tokens arrive on the
# same event channel. Only the tag tells them apart — without this filter the
# title is appended to the visible answer.
TITLE_TAG = "chat-title"


def _sse(chunk: dict[str, Any]) -> str:
    """Frame one UI message chunk as an SSE event."""
    return f"data: {json.dumps(chunk)}\n\n"


def _chunk_text(chunk: Any) -> str:
    """Pull plain text out of a LangChain AIMessageChunk.

    `content` is a str for ChatOpenAI, but the multimodal block list is part of
    the interface, so both shapes are handled.
    """
    content = getattr(chunk, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        )
    return ""


def _tool_output(output: Any) -> Any:
    """Unwrap a ToolMessage into something JSON-serialisable."""
    content = getattr(output, "content", output)
    if isinstance(content, str | int | float | bool | list | dict) or content is None:
        return content
    return str(content)


async def langgraph_to_ai_sdk_stream(
    events: AsyncIterator,
    message_id: str | None = None,
) -> AsyncGenerator[str]:
    """Convert LangGraph astream_events (v2) to the AI SDK UI Message Stream.

    Handles:
    - `on_chat_model_stream` → text-delta
    - `on_chat_model_end`    → text-end (a tool loop yields one part per step)
    - `on_tool_start`        → tool-input-available
    - `on_tool_end`          → tool-output-available
    - `on_custom_event`      → data-chat-title (transient)

    Anything tagged `chat-title` is dropped: that is the title generation
    running on the same model, and its tokens are not part of the answer.

    `message_id` is streamed as the assistant message's id so the rendered
    message matches the row persisted by the graph — votes and edits key off it.
    """
    start: dict[str, Any] = {"type": "start"}
    if message_id:
        start["messageId"] = message_id
    yield _sse(start)
    yield _sse({"type": "start-step"})

    text_id: str | None = None
    try:
        async for event in events:
            kind = event.get("event")
            data = event.get("data", {})

            if TITLE_TAG in (event.get("tags") or []):
                continue

            if kind == "on_custom_event" and event.get("name") == "chat_title":
                # Transient: the sidebar and header consume it, but it is not
                # part of the assistant message and must not be stored in it.
                yield _sse({"type": "data-chat-title", "data": data, "transient": True})

            elif kind == "on_chat_model_stream":
                delta = _chunk_text(data.get("chunk"))
                if not delta:
                    continue
                if text_id is None:
                    text_id = uuid.uuid4().hex
                    yield _sse({"type": "text-start", "id": text_id})
                yield _sse({"type": "text-delta", "id": text_id, "delta": delta})

            elif kind == "on_chat_model_end":
                if text_id is not None:
                    yield _sse({"type": "text-end", "id": text_id})
                    text_id = None

            elif kind == "on_tool_start":
                yield _sse(
                    {
                        "type": "tool-input-available",
                        "toolCallId": event.get("run_id", ""),
                        "toolName": event.get("name", "unknown_tool"),
                        "input": data.get("input", {}),
                    }
                )

            elif kind == "on_tool_end":
                yield _sse(
                    {
                        "type": "tool-output-available",
                        "toolCallId": event.get("run_id", ""),
                        "output": _tool_output(data.get("output")),
                    }
                )

    except Exception as e:
        logger.exception("Error in LangGraph stream")
        if text_id is not None:
            yield _sse({"type": "text-end", "id": text_id})
            text_id = None
        yield _sse({"type": "error", "errorText": str(e)})

    # An unclosed text part renders as nothing, so close it on every exit path.
    if text_id is not None:
        yield _sse({"type": "text-end", "id": text_id})

    yield _sse({"type": "finish-step"})
    yield _sse({"type": "finish"})
    yield DONE
