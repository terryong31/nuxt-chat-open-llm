import json
from collections.abc import AsyncGenerator

import httpx
from app.core.config import get_settings


class LLMClient:
    """HTTP Client to delegate inference generation to the dedicated apps/llm microservice."""

    @staticmethod
    async def stream_chat_completion(
        messages: list[dict], model: str = ""
    ) -> AsyncGenerator[str]:
        settings = get_settings()
        url = f"{settings.llm_engine_url}/v1/chat/completions"

        payload = {
            "model": model or "mlx-community/Mamba-Codestral-7B-v0.1-4bit",
            "messages": messages,
            "stream": True,
        }

        async with (
            httpx.AsyncClient(timeout=120.0) as client,
            client.stream("POST", url, json=payload) as response,
        ):
            if response.status_code != 200:
                yield f"data: {json.dumps({'error': 'LLM engine error'})}\n\n"
                return

            async for line in response.aiter_lines():
                if line:
                    yield f"{line}\n\n"
