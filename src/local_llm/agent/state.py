from typing import TypedDict, Annotated, Sequence, Dict, Any, List
import operator


class AgentState(TypedDict):
    """
    LangGraph ReAct Agent State Definition.
    Tracks conversation message list, extracted tool calls, and accumulated outputs.
    """
    messages: Annotated[Sequence[Dict[str, Any]], operator.add]
    tool_calls: List[Dict[str, Any]]
    tool_results: List[Dict[str, Any]]
