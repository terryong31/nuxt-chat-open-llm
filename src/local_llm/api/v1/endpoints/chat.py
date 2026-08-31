import time
import json
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from mlx_lm import stream_generate
from mlx_lm.sample_utils import make_sampler
from local_llm.core.config import settings
from local_llm.schemas.chat import ChatRequest, ChatResponse
from local_llm.schemas.metrics import MetricsResponse
from local_llm.models.manager import ModelManager
from local_llm.agent.engine import stream_graph_chat

router = APIRouter(prefix="/chat", tags=["Chat"])


def generate_complete(
    messages_payload: list,
    thinking_budget: int,
    max_tokens: int,
    temperature: float,
    top_p: float,
) -> ChatResponse:
    """Synchronous fallback completion generator."""
    model = ModelManager.model
    tokenizer = ModelManager.tokenizer
    if not model or not tokenizer:
        raise HTTPException(status_code=500, detail="Model is not initialized")

    sampler = make_sampler(temp=temperature, top_p=top_p)

    try:
        if thinking_budget == 0:
            try:
                prompt = tokenizer.apply_chat_template(
                    messages_payload, tokenize=False, add_generation_prompt=True, enable_thinking=False
                )
            except TypeError:
                prompt = tokenizer.apply_chat_template(
                    messages_payload, tokenize=False, add_generation_prompt=True
                ) + "\n</think>\n\n"
        else:
            prompt = tokenizer.apply_chat_template(
                messages_payload, tokenize=False, add_generation_prompt=True
            )
    except Exception:
        prompt = "\n".join(f"{m['role']}: {m['content']}" for m in messages_payload) + "\nassistant:"

    start_time = time.perf_counter()
    full_response = ""
    thinking_text = ""
    answer_text = ""
    in_thinking = thinking_budget > 0
    thinking_tokens = 0
    answer_tokens = 0
    prompt_tokens = 0
    prompt_tps = 0.0
    peak_mem = 0.0
    budget_exceeded = False

    for res in stream_generate(
        model=model, tokenizer=tokenizer, prompt=prompt, max_tokens=max_tokens, sampler=sampler
    ):
        prompt_tokens = res.prompt_tokens
        prompt_tps = res.prompt_tps
        peak_mem = res.peak_memory

        if in_thinking:
            thinking_tokens += 1
            accumulated = thinking_text + res.text
            if "</think>" in accumulated:
                think_part, after_think = accumulated.split("</think>", 1)
                thinking_text = think_part
                clean_after = after_think.lstrip("\n")
                answer_text += clean_after
                full_response = think_part + "</think>\n\n" + after_think
                in_thinking = False
            else:
                if thinking_tokens >= thinking_budget:
                    thinking_text += res.text
                    budget_exceeded = True
                    break
                else:
                    thinking_text += res.text
        else:
            answer_tokens += 1
            answer_text += res.text
            full_response += res.text

    if budget_exceeded:
        continued_prompt = prompt + thinking_text + "\n</think>\n\n"
        remaining_tokens = max(1, max_tokens - thinking_tokens)
        for res in stream_generate(
            model=model, tokenizer=tokenizer, prompt=continued_prompt, max_tokens=remaining_tokens, sampler=sampler
        ):
            peak_mem = res.peak_memory
            answer_tokens = res.generation_tokens
            answer_text += res.text
            full_response += res.text

    elapsed_time = time.perf_counter() - start_time
    total_tokens = thinking_tokens + answer_tokens
    gen_tps = total_tokens / elapsed_time if elapsed_time > 0 else 0.0

    return ChatResponse(
        response=answer_text.strip(),
        thinking=thinking_text.strip(),
        metrics=MetricsResponse(
            total_tokens=total_tokens,
            thinking_tokens=thinking_tokens,
            answer_tokens=answer_tokens,
            generation_tps=round(gen_tps, 2),
            elapsed_time_sec=round(elapsed_time, 2),
            prompt_tokens=prompt_tokens,
            prompt_tps=round(prompt_tps, 2),
            peak_memory_gb=round(peak_mem, 2),
        ),
    )


def stream_tokens_generator(
    messages_payload: list,
    thinking_budget: int,
    max_tokens: int,
    temperature: float,
    top_p: float,
):
    """SSE Token Streaming Generator."""
    model = ModelManager.model
    tokenizer = ModelManager.tokenizer
    if not model or not tokenizer:
        yield f"data: {json.dumps({'error': 'Model not loaded'})}\n\n"
        return

    yield from stream_graph_chat(
        model=model,
        tokenizer=tokenizer,
        messages_payload=messages_payload,
        thinking_budget=thinking_budget,
        max_tokens=max_tokens,
        temperature=temperature,
        top_p=top_p,
    )


@router.post("", response_model=ChatResponse)
def chat_endpoint(request: ChatRequest):
    """
    Main Chat Completion Endpoint:
    - Instantly activates model from preloaded in-memory cache
    - Streams SSE tokens or returns single JSON response
    """
    target_model = request.model or settings.DEFAULT_MODEL
    ModelManager.activate_model(target_model)

    payload_messages = [msg.model_dump() for msg in request.messages]

    if request.stream:
        return StreamingResponse(
            stream_tokens_generator(
                messages_payload=payload_messages,
                thinking_budget=request.thinking_budget,
                max_tokens=request.max_tokens,
                temperature=request.temperature,
                top_p=request.top_p,
            ),
            media_type="text/event-stream",
        )

    return generate_complete(
        messages_payload=payload_messages,
        thinking_budget=request.thinking_budget,
        max_tokens=request.max_tokens,
        temperature=request.temperature,
        top_p=request.top_p,
    )
