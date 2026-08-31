from typing import List, Optional, Literal
from pydantic import BaseModel, Field
from local_llm.core.config import settings
from local_llm.schemas.metrics import MetricsResponse


class ChatMessage(BaseModel):
    """Single chat message format."""
    role: Literal["system", "user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    """Incoming chat completion request."""
    messages: List[ChatMessage] = Field(
        ..., description="Full conversation history (stateless)"
    )
    model: Optional[str] = Field(
        None, description="Hugging Face / MLX model ID to run"
    )
    thinking_budget: Optional[int] = Field(
        settings.DEFAULT_THINKING_BUDGET,
        description="Max tokens for thinking process (0 to disable)",
    )
    max_tokens: Optional[int] = Field(
        settings.DEFAULT_MAX_TOKENS, description="Max generated tokens"
    )
    temperature: Optional[float] = Field(
        settings.DEFAULT_TEMPERATURE, ge=0.0, le=2.0
    )
    top_p: Optional[float] = Field(
        settings.DEFAULT_TOP_P, ge=0.0, le=1.0
    )
    stream: Optional[bool] = Field(
        False, description="Whether to stream tokens via Server-Sent Events (SSE)"
    )


class ChatResponse(BaseModel):
    """Synchronous chat completion response."""
    response: str
    thinking: str
    metrics: MetricsResponse
