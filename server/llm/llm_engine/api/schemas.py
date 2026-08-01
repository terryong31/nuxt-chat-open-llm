from typing import Literal

from pydantic import BaseModel


class FunctionCall(BaseModel):
    name: str
    # OpenAI sends arguments as a JSON *string*, not an object. langchain-openai
    # parses it back, so emitting an object here silently breaks tool binding.
    arguments: str


class ToolCallSpec(BaseModel):
    id: str
    type: Literal["function"] = "function"
    function: FunctionCall


class FunctionDef(BaseModel):
    name: str
    description: str = ""
    parameters: dict = {}


class ToolDef(BaseModel):
    type: Literal["function"] = "function"
    function: FunctionDef


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    # Absent on an assistant turn that only asked for tools.
    content: str | None = None
    tool_calls: list[ToolCallSpec] | None = None
    tool_call_id: str | None = None


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
    tools: list[ToolDef] | None = None
    # Accepted so clients that always send it do not 422. Only "none" changes
    # behaviour here; the checkpoint decides the rest on its own.
    tool_choice: str | dict | None = None

    @property
    def resolved_max_tokens(self) -> int | None:
        """Either spelling, new name first."""
        return self.max_completion_tokens or self.max_tokens


class ChatCompletionChoiceMessage(BaseModel):
    role: str = "assistant"
    content: str | None = None
    tool_calls: list[ToolCallSpec] | None = None


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
