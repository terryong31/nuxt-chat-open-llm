from typing import Annotated

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class AgentState(TypedDict):
    """State that flows through the LangGraph agent graph."""

    chat_id: str
    user_id: str
    model: str
    # Minted by the router so the streamed message and the persisted row share
    # an id — votes and edit/regenerate key off it.
    assistant_message_id: str
    # Set by load_history: true only while the chat still has no title, so a
    # title the user typed is never overwritten on a later turn.
    needs_title: bool
    messages: Annotated[list[BaseMessage], add_messages]
