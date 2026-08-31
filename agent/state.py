from typing import TypedDict, Annotated, Sequence, Any
from langchain_core.messages import BaseMessage
import operator


class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], operator.add]
    thinking_budget: int
    max_tokens: int
    temperature: float
    top_p: float
    raw_history: list[dict[str, Any]]
