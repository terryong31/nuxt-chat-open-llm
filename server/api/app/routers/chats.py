import uuid
from typing import Annotated, Any

from app.agent.graph import build_graph
from app.agent.stream import langgraph_to_ai_sdk_stream
from app.core.security import get_current_user
from app.services.chat_service import ChatService
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage
from pydantic import BaseModel

router = APIRouter(prefix="/v1/chats", tags=["chats"])
CurrentUser = Annotated[dict, Depends(get_current_user)]


class MessageCreate(BaseModel):
    id: str | None = None
    role: str
    parts: Any


class ChatCreate(BaseModel):
    id: str | None = None
    message: MessageCreate


class TitleUpdate(BaseModel):
    title: str


class VisibilityUpdate(BaseModel):
    visibility: str


class VoteRequest(BaseModel):
    messageId: str
    isUpvoted: bool | None = None


class MessageDeleteRequest(BaseModel):
    messageId: str
    type: str  # "edit" | "regenerate"


@router.get("")
async def list_chats(current_user: CurrentUser):
    return ChatService.list_chats(current_user["id"])


@router.post("")
async def create_chat(payload: ChatCreate, current_user: CurrentUser):
    try:
        return ChatService.create_chat(
            user_id=current_user["id"],
            chat_id=payload.id,
            message=payload.message.model_dump(),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/{id}")
async def get_chat(id: str, current_user: CurrentUser):
    try:
        return ChatService.get_chat(id, current_user["id"])
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.patch("/{id}/title")
async def update_title(id: str, payload: TitleUpdate, current_user: CurrentUser):
    try:
        return ChatService.update_title(id, current_user["id"], payload.title)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.patch("/{id}/visibility")
async def update_visibility(
    id: str, payload: VisibilityUpdate, current_user: CurrentUser
):
    try:
        return ChatService.update_visibility(id, current_user["id"], payload.visibility)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.delete("/{id}")
async def delete_chat(id: str, current_user: CurrentUser):
    username = (
        current_user.get("user_metadata", {}).get("preferred_username")
        or current_user["id"]
    )
    return ChatService.delete_chat(id, current_user["id"], username)


@router.get("/{id}/votes")
async def list_votes(id: str, current_user: CurrentUser):
    return ChatService.list_votes(id)


@router.post("/{id}/votes")
async def toggle_vote(id: str, payload: VoteRequest, current_user: CurrentUser):
    return ChatService.toggle_vote(id, payload.messageId, payload.isUpvoted)


@router.delete("/{id}/messages")
async def delete_messages(
    id: str,
    payload: MessageDeleteRequest,
    current_user: CurrentUser,
):
    try:
        ChatService.delete_messages(id, payload.messageId, payload.type)
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/{id}/stream")
async def stream_chat(id: str, payload: dict, current_user: CurrentUser):
    """Stream AI response via LangGraph agent using the AI SDK UI Message Stream."""
    messages = payload.get("messages", [])
    model = payload.get("model", "")
    user_id = current_user["id"]

    # Extract last user message to seed the agent turn
    last_user_msg = next(
        (m for m in reversed(messages) if m.get("role") == "user"),
        None,
    )
    if not last_user_msg:
        raise HTTPException(status_code=400, detail="No user message in payload")

    # Extract text content from AI SDK parts format
    parts = last_user_msg.get("parts", [])
    text = " ".join(p.get("text", "") for p in parts if p.get("type") == "text")
    if not text:
        text = last_user_msg.get("content", "")

    # Persist the user turn before generating: the client only ever POSTs the
    # transcript, and `create_chat` covers the first message alone, so without
    # this every turn after the first vanishes on reload. Writing it here also
    # makes the DB the single source of truth that `load_history` reads back.
    saved = ChatService.save_message(
        chat_id=id,
        role="user",
        parts=parts or [{"type": "text", "text": text}],
        message_id=last_user_msg.get("id"),
    )

    graph = build_graph(model)
    assistant_message_id = str(uuid.uuid4())
    initial_state = {
        "chat_id": id,
        "user_id": user_id,
        "model": model,
        "assistant_message_id": assistant_message_id,
        # Empty unless the write above failed — `load_history` supplies the turn
        # from the DB, and seeding it here too would duplicate it in the prompt.
        "messages": [] if saved else [HumanMessage(content=text)],
    }

    events = graph.astream_events(initial_state, version="v2")

    return StreamingResponse(
        langgraph_to_ai_sdk_stream(events, message_id=assistant_message_id),
        media_type="text/event-stream",
        headers={
            "x-vercel-ai-ui-message-stream": "v1",
            "cache-control": "no-cache",
            "connection": "keep-alive",
            "x-accel-buffering": "no",  # keep proxies from buffering the stream
        },
    )
