from functools import lru_cache

from app.core.config import get_settings

from supabase import Client, create_client


@lru_cache
def get_supabase_admin() -> Client:
    """Returns a singleton Supabase Client initialized with the Service Role Key.

    This client bypasses RLS policies and must only be used on the backend after
    validating the user's JWT.
    """
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_service_key:
        return create_client(
            settings.supabase_url or "https://placeholder.supabase.co",
            settings.supabase_service_key or "placeholder-key",
        )
    return create_client(settings.supabase_url, settings.supabase_service_key)
