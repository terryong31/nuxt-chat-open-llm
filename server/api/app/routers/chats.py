from typing import Annotated, Any

from app.core.security import get_current_user
from app.services.chat_service import ChatService
from app.services.llm_client import LLMClient
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
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
    """Stream AI response from apps/llm and push output tokens."""
    messages = payload.get("messages", [])
    model = payload.get("model", "")
    return StreamingResponse(
        LLMClient.stream_chat_completion(messages, model),
        media_type="text/event-stream",
    )
