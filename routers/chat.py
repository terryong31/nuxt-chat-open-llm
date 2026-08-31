import time
import json
from typing import List, Optional, Literal
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from mlx_lm import load, stream_generate
from mlx_lm.sample_utils import make_sampler
import gc
import mlx.core as mx

router = APIRouter(prefix="/chat", tags=["Chat"])

DEFAULT_MODEL = "mlx-community/Qwen3.5-9B-MLX-8bit"
DEFAULT_TEMP = 0.7
DEFAULT_TOP_P = 0.9
DEFAULT_MAX_TOKENS = 2048
DEFAULT_THINKING_BUDGET = 100

SUPPORTED_MODELS = [
    "mlx-community/Qwen3.5-9B-MLX-8bit",
    "mlx-community/Qwen3.8-27B-4bit",
]


# Global Model Manager with Preloading, Instant Switching, and Unified Memory Flush
class ModelManager:
    _loaded_models: dict[str, tuple] = {}
    model = None
    tokenizer = None
    model_id: Optional[str] = DEFAULT_MODEL

    @classmethod
    def preload_all_models(cls):
        """
        Preloads all supported models into Unified Memory at application startup.
        """
        print("🚀 Preloading all local MLX models into Unified Memory...")
        for mid in SUPPORTED_MODELS:
            if mid not in cls._loaded_models:
                print(f"📦 Preloading {mid} ...")
                try:
                    m, t, *_ = load(mid)
                    cls._loaded_models[mid] = (m, t)
                    print(f"✓ Model {mid} preloaded & cached!")
                except Exception as e:
                    print(f"⚠️ Failed to preload {mid}: {e}")

        # Set default active model
        if DEFAULT_MODEL in cls._loaded_models:
            cls.activate_model(DEFAULT_MODEL)
        elif cls._loaded_models:
            first_mid = next(iter(cls._loaded_models))
            cls.activate_model(first_mid)
        print(f"✨ Models in memory: {list(cls._loaded_models.keys())} | Active default: {cls.model_id}")

    @classmethod
    def activate_model(cls, model_id: str):
        """
        Activates the requested model when called via API.
        If already in cache, activation is instantaneous (0.0s delay).
        """
        if model_id in cls._loaded_models:
            if cls.model_id != model_id or cls.model is None:
                cls.model, cls.tokenizer = cls._loaded_models[model_id]
                cls.model_id = model_id
                print(f"⚡ Activated model: {model_id} (instant memory switch)")
        else:
            print(f"🚀 Model {model_id} not in cache, loading on-demand...")
            try:
                m, t, *_ = load(model_id)
                cls._loaded_models[model_id] = (m, t)
                cls.model, cls.tokenizer = m, t
                cls.model_id = model_id
                print(f"✓ Model {model_id} loaded & cached!")
            except Exception as e:
                print(f"⚠️ Failed to load {model_id}, falling back to {DEFAULT_MODEL}: {e}")
                if DEFAULT_MODEL in cls._loaded_models:
                    cls.activate_model(DEFAULT_MODEL)

    @classmethod
    def load_model(cls, model_id: str = DEFAULT_MODEL):
        """Legacy alias pointing to activate_model."""
        cls.activate_model(model_id)

    @classmethod
    def unload_model(cls):
        """Legacy alias pointing to unload_all."""
        cls.unload_all()

    @classmethod
    def unload_all(cls):
        """
        Flushes all models from Unified Memory and clears MLX cache on shutdown.
        """
        print("🧹 Flushing all MLX models from Unified Memory...")
        cls._loaded_models.clear()
        cls.model = None
        cls.tokenizer = None
        cls.model_id = None
        gc.collect()
        try:
            if hasattr(mx, "clear_cache"):
                mx.clear_cache()
            elif hasattr(mx, "metal") and hasattr(mx.metal, "clear_cache"):
                mx.metal.clear_cache()
        except Exception:
            pass
        print("✓ All Unified Memory and MLX cache fully flushed!")


# --- Pydantic Request / Response Schemas ---
class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    messages: List[ChatMessage] = Field(
        ..., description="Full conversation history (stateless)"
    )
    model: Optional[str] = Field(
        None, description="Hugging Face / MLX model ID to run"
    )
    thinking_budget: Optional[int] = Field(
        DEFAULT_THINKING_BUDGET,
        description="Max tokens for thinking process (0 to disable)",
    )
    max_tokens: Optional[int] = Field(DEFAULT_MAX_TOKENS, description="Max generated tokens")
    temperature: Optional[float] = Field(DEFAULT_TEMP, ge=0.0, le=2.0)
    top_p: Optional[float] = Field(DEFAULT_TOP_P, ge=0.0, le=1.0)
    stream: Optional[bool] = Field(
        False, description="Whether to stream tokens via Server-Sent Events (SSE)"
    )


class MetricsResponse(BaseModel):
    total_tokens: int
    thinking_tokens: int
    answer_tokens: int
    generation_tps: float
    elapsed_time_sec: float
    prompt_tokens: int
    prompt_tps: float
    peak_memory_gb: float


class ChatResponse(BaseModel):
    response: str
    thinking: str
    metrics: MetricsResponse


# --- Helper: Generate Complete Response (Non-Streaming) ---
def generate_complete(
    messages_payload: list,
    thinking_budget: int,
    max_tokens: int,
    temperature: float,
    top_p: float,
) -> ChatResponse:
    model = ModelManager.model
    tokenizer = ModelManager.tokenizer
    if not model or not tokenizer:
        raise HTTPException(status_code=500, detail="Model is not initialized")

    sampler = make_sampler(temp=temperature, top_p=top_p)

    # Format Prompt
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

    # Stage 1: Initial stream
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

    # Stage 2: Fallback if thinking budget was exceeded
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


# --- Helper: Token Streaming Generator (SSE) ---
def stream_tokens_generator(
    messages_payload: list,
    thinking_budget: int,
    max_tokens: int,
    temperature: float,
    top_p: float,
):
    model = ModelManager.model
    tokenizer = ModelManager.tokenizer
    if not model or not tokenizer:
        yield f"data: {json.dumps({'error': 'Model not loaded'})}\n\n"
        return

    from agent.graph import stream_graph_chat

    yield from stream_graph_chat(
        model=model,
        tokenizer=tokenizer,
        messages_payload=messages_payload,
        thinking_budget=thinking_budget,
        max_tokens=max_tokens,
        temperature=temperature,
        top_p=top_p,
    )


# --- API Endpoint ---
@router.post("", response_model=ChatResponse)
def chat_endpoint(request: ChatRequest):
    """
    Main Chat Completion Endpoint
    - Instant model activation from preloaded cache
    - Supports single JSON responses or SSE streaming
    - Fully compatible with OpenAI-style message lists
    """
    target_model = request.model or DEFAULT_MODEL
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
