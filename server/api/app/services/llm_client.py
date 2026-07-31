import json
import logging
from collections.abc import AsyncGenerator

import httpx
from app.core.config import get_settings

logger = logging.getLogger(__name__)


def _normalise_messages(messages: list[dict]) -> list[dict]:
    """Convert AI SDK message format to OpenAI format.

    AI SDK sends: {"role": "user", "parts": [{"type": "text", "text": "..."}]}
    OpenAI expects: {"role": "user", "content": "..."}
    """
    result = []
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content")

        if content is None:
            # AI SDK parts format
            parts = m.get("parts", [])
            text_parts = [p.get("text", "") for p in parts if p.get("type") == "text"]
            content = " ".join(text_parts)

        if isinstance(content, list):
            # OpenAI multipart array — extract text
            content = " ".join(
                p.get("text", "")
                for p in content
                if isinstance(p, dict) and p.get("type") == "text"
            )

        result.append({"role": role, "content": content})
    return result


class LLMClient:
    """HTTP Client to delegate inference generation to the LLM microservice.

    Translates AI SDK message format → OpenAI format (inbound),
    and OpenAI SSE chunks → AI SDK Data Stream Protocol (outbound).
    """

    @staticmethod
    async def stream_chat_completion(
        messages: list[dict], model: str = ""
    ) -> AsyncGenerator[str]:
        settings = get_settings()
        url = f"{settings.llm_engine_url}/v1/chat/completions"

        openai_messages = _normalise_messages(messages)

        payload = {
            "model": model or settings.model_id,
            "messages": openai_messages,
            "stream": True,
        }

        try:
            async with (
                httpx.AsyncClient(timeout=120.0) as client,
                client.stream("POST", url, json=payload) as response,
            ):
                if response.status_code != 200:
                    body = await response.aread()
                    logger.error(
                        "LLM engine error %s: %s", response.status_code, body.decode()
                    )
                    yield f"3:{json.dumps('LLM engine unavailable')}\n"
                    return

                async for line in response.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    raw = line[6:]  # strip "data: "
                    if raw == "[DONE]":
                        # Final finish event
                        yield f"d:{json.dumps({'finishReason': 'stop', 'usage': {'promptTokens': 0, 'completionTokens': 0}})}\n"
                        return

                    try:
                        chunk = json.loads(raw)
                        delta = chunk["choices"][0]["delta"]
                        text = delta.get("content")
                        if text:
                            yield f"0:{json.dumps(text)}\n"
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue

        except httpx.ConnectError:
            logger.error("Cannot connect to LLM engine at %s", url)
            yield f"3:{json.dumps('LLM engine is not running')}\n"
