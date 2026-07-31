import logging
import uuid

from app.services.supabase import get_supabase_admin
from fastapi import HTTPException

logger = logging.getLogger(__name__)


class ChatService:
    @staticmethod
    def list_chats(user_id: str) -> list[dict]:
        supabase = get_supabase_admin()
        res = (
            supabase.table("chats")
            .select("*")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .execute()
        )
        return res.data or []

    @staticmethod
    def create_chat(user_id: str, chat_id: str | None, message: dict) -> dict:
        supabase = get_supabase_admin()
        cid = chat_id or str(uuid.uuid4())
        mid = message.get("id") or str(uuid.uuid4())

        chat_res = (
            supabase.table("chats")
            .insert({"id": cid, "title": "", "user_id": user_id})
            .execute()
        )

        if not chat_res.data:
            raise HTTPException(status_code=500, detail="Failed creating chat")

        supabase.table("messages").insert(
            {
                "id": mid,
                "chat_id": cid,
                "role": message.get("role", "user"),
                "parts": message.get("parts"),
            }
        ).execute()

        return chat_res.data[0]

    @staticmethod
    def get_chat(chat_id: str, user_id: str) -> dict:
        supabase = get_supabase_admin()
        chat_res = (
            supabase.table("chats").select("*, messages(*)").eq("id", chat_id).execute()
        )
        if not chat_res.data:
            raise HTTPException(status_code=404, detail="Chat not found")

        chat = chat_res.data[0]
        is_owner = chat.get("user_id") == user_id

        if chat.get("visibility") == "private" and not is_owner:
            raise HTTPException(status_code=404, detail="Chat not found")

        messages = chat.get("messages") or []
        messages.sort(key=lambda m: m.get("created_at", ""))

        return {**chat, "isOwner": is_owner, "messages": messages}

    @staticmethod
    def update_title(chat_id: str, user_id: str, title: str) -> dict:
        supabase = get_supabase_admin()
        res = (
            supabase.table("chats")
            .update({"title": title})
            .eq("id", chat_id)
            .eq("user_id", user_id)
            .execute()
        )
        if not res.data:
            raise HTTPException(status_code=404, detail="Chat not found")
        return res.data[0]

    @staticmethod
    def update_visibility(chat_id: str, user_id: str, visibility: str) -> dict:
        supabase = get_supabase_admin()
        res = (
            supabase.table("chats")
            .update({"visibility": visibility})
            .eq("id", chat_id)
            .eq("user_id", user_id)
            .execute()
        )
        if not res.data:
            raise HTTPException(status_code=404, detail="Chat not found")
        return res.data[0]

    @staticmethod
    def delete_chat(chat_id: str, user_id: str, username: str) -> list[dict]:
        supabase = get_supabase_admin()
        chat_folder = f"{username}/{chat_id}"

        try:
            files = supabase.storage.from_("chat-attachments").list(chat_folder)
            if files:
                file_paths = [f"{chat_folder}/{f['name']}" for f in files]
                supabase.storage.from_("chat-attachments").remove(file_paths)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[delete-chat] Storage cleanup issue: {e}")

        res = (
            supabase.table("chats")
            .delete()
            .eq("id", chat_id)
            .eq("user_id", user_id)
            .execute()
        )
        return res.data or []

    @staticmethod
    def list_votes(chat_id: str) -> list[dict]:
        supabase = get_supabase_admin()
        res = supabase.table("votes").select("*").eq("chat_id", chat_id).execute()
        return res.data or []

    @staticmethod
    def toggle_vote(chat_id: str, message_id: str, is_upvoted: bool | None) -> dict:
        supabase = get_supabase_admin()
        if is_upvoted is None:
            supabase.table("votes").delete().eq("chat_id", chat_id).eq(
                "message_id", message_id
            ).execute()
        else:
            supabase.table("votes").upsert(
                {"chat_id": chat_id, "message_id": message_id, "is_upvoted": is_upvoted}
            ).execute()
        return {"chatId": chat_id, "messageId": message_id, "isUpvoted": is_upvoted}

    @staticmethod
    def delete_messages(chat_id: str, message_id: str, delete_type: str) -> bool:
        supabase = get_supabase_admin()
        msgs_res = (
            supabase.table("messages")
            .select("id, role, created_at")
            .eq("chat_id", chat_id)
            .order("created_at", desc=False)
            .execute()
        )
        all_msgs = msgs_res.data or []

        target_idx = next(
            (i for i, m in enumerate(all_msgs) if m["id"] == message_id), -1
        )
        if target_idx == -1:
            raise HTTPException(status_code=404, detail="Message not found")

        start_idx = target_idx + 1 if delete_type == "edit" else target_idx
        ids_to_delete = [m["id"] for m in all_msgs[start_idx:]]

        if ids_to_delete:
            supabase.table("messages").delete().in_("id", ids_to_delete).execute()

        return True
