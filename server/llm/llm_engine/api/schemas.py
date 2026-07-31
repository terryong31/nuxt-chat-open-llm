from typing import Literal

from pydantic import BaseModel


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class ChatCompletionRequest(BaseModel):
    model: str
    messages: list[ChatMessage]
    temperature: float | None = None
    top_p: float | None = None
    max_tokens: int | None = None
    # OpenAI renamed `max_tokens` to this, and current clients send only the new
    # name -- langchain-openai rewrites `max_tokens` into it unconditionally.
    # Accepting one name only meant the budget was silently dropped and every
    # reply came back at the server default.
    max_completion_tokens: int | None = None
    stream: bool = False

    @property
    def resolved_max_tokens(self) -> int | None:
        """Either spelling, new name first."""
        return self.max_completion_tokens or self.max_tokens


class ChatCompletionChoiceMessage(BaseModel):
    role: str = "assistant"
    content: str


class ChatCompletionChoice(BaseModel):
    index: int = 0
    message: ChatCompletionChoiceMessage
    finish_reason: str = "stop"


class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: list[ChatCompletionChoice]


class ErrorBody(BaseModel):
    message: str
    type: str


class ErrorResponse(BaseModel):
    error: ErrorBody
