import logging
import uuid

from app.core.config import get_settings
from app.services.supabase import get_supabase_admin
from fastapi import HTTPException

logger = logging.getLogger(__name__)


def _as_uuid(value: str | None) -> str:
    """Coerce a client-supplied id into something `messages.id` accepts.

    That column is `uuid`, and `votes.message_id` points at it, so a non-UUID
    id is rejected by Postgres and the row is lost. The AI SDK's own generator
    emits nanoid-style strings, which is exactly that case: every turn after
    the first vanished, and the model saw a conversation with one user message
    and a pile of assistant replies. The client now mints UUIDs; this keeps a
    future client change from silently costing history again.
    """
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, TypeError):
        if value is not None:
            logger.warning("non-uuid message id %r; minting one instead", value)
        return str(uuid.uuid4())


class ChatService:
    @staticmethod
    def list_chats(user_id: str) -> list[dict]:
        supabase = get_supabase_admin()
        settings = get_settings()
        query = supabase.table("chats").select("*")
        if settings.app_env != "development":
            query = query.eq("user_id", user_id)
        res = query.order("created_at", desc=True).execute()
        return res.data or []

    @staticmethod
    def create_chat(user_id: str, chat_id: str | None, message: dict) -> dict:
        supabase = get_supabase_admin()
        cid = _as_uuid(chat_id)
        mid = _as_uuid(message.get("id"))

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
    def save_message(
        chat_id: str,
        role: str,
        parts: list | dict,
        message_id: str | None = None,
    ) -> dict | None:
        """Upsert one message row. Returns None on failure rather than raising.

        Callers are mid-stream: a failed write should degrade history, not kill
        the response the user is waiting on. Upsert makes a retried or
        regenerated turn idempotent on the client-supplied id.
        """
        supabase = get_supabase_admin()
        row = {
            "id": _as_uuid(message_id),
            "chat_id": chat_id,
            "role": role,
            "parts": parts,
        }
        try:
            res = supabase.table("messages").upsert(row).execute()
            return (res.data or [row])[0]
        except Exception as e:  # noqa: BLE001
            logger.error("save_message failed for chat %s: %s", chat_id, e)
            return None

    @staticmethod
    def get_title(chat_id: str) -> str:
        """Current title, or "" if unset. Cheap single-row lookup."""
        supabase = get_supabase_admin()
        try:
            res = (
                supabase.table("chats")
                .select("title")
                .eq("id", chat_id)
                .limit(1)
                .execute()
            )
            return (res.data or [{}])[0].get("title") or ""
        except Exception as e:  # noqa: BLE001
            logger.error("get_title failed for chat %s: %s", chat_id, e)
            return ""

    @staticmethod
    def set_title(chat_id: str, title: str) -> bool:
        """Write a title without the ownership check `update_title` enforces.

        The agent already ran against an authorised request; this is a
        mid-stream write, so it logs and moves on rather than raising.
        """
        supabase = get_supabase_admin()
        try:
            supabase.table("chats").update({"title": title}).eq("id", chat_id).execute()
            return True
        except Exception as e:  # noqa: BLE001
            logger.error("set_title failed for chat %s: %s", chat_id, e)
            return False

    @staticmethod
    def get_chat(chat_id: str, user_id: str) -> dict:
        supabase = get_supabase_admin()
        settings = get_settings()
        chat_res = (
            supabase.table("chats")
            .select("*, messages!messages_chat_id_fkey(*)")
            .eq("id", chat_id)
            .execute()
        )
        if not chat_res.data:
            raise HTTPException(status_code=404, detail="Chat not found")

        chat = chat_res.data[0]
        is_owner = (chat.get("user_id") == user_id) or (
            settings.app_env == "development"
        )

        if chat.get("visibility") == "private" and not is_owner:
            raise HTTPException(status_code=404, detail="Chat not found")

        messages = chat.get("messages") or []
        messages.sort(key=lambda m: m.get("created_at", ""))

        return {**chat, "isOwner": is_owner, "messages": messages}

    @staticmethod
    def update_title(chat_id: str, user_id: str, title: str) -> dict:
        supabase = get_supabase_admin()
        settings = get_settings()
        query = supabase.table("chats").update({"title": title}).eq("id", chat_id)
        if settings.app_env != "development":
            query = query.eq("user_id", user_id)
        res = query.execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="Chat not found")
        return res.data[0]

    @staticmethod
    def update_visibility(chat_id: str, user_id: str, visibility: str) -> dict:
        supabase = get_supabase_admin()
        settings = get_settings()
        query = (
            supabase.table("chats").update({"visibility": visibility}).eq("id", chat_id)
        )
        if settings.app_env != "development":
            query = query.eq("user_id", user_id)
        res = query.execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="Chat not found")
        return res.data[0]

    @staticmethod
    def delete_chat(chat_id: str, user_id: str, username: str) -> list[dict]:
        supabase = get_supabase_admin()
        settings = get_settings()
        chat_folder = f"{username}/{chat_id}"

        try:
            files = supabase.storage.from_("chat-attachments").list(chat_folder)
            if files:
                file_paths = [f"{chat_folder}/{f['name']}" for f in files]
                supabase.storage.from_("chat-attachments").remove(file_paths)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[delete-chat] Storage cleanup issue: {e}")

        query = supabase.table("chats").delete().eq("id", chat_id)
        if settings.app_env != "development":
            query = query.eq("user_id", user_id)
        res = query.execute()
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
