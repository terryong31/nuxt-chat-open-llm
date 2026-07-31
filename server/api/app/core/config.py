import os
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

app_env = os.getenv("APP_ENV", "development")


class Settings(BaseSettings):
    app_env: str = app_env
    model_config = SettingsConfigDict(
        env_prefix="LLM_",
        env_file=(".env", f".env.{app_env}"),
        extra="ignore",
        protected_namespaces=(),
    )

    # -- server -------------------------------------------------------------
    host: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "INFO"

    # -- supabase -----------------------------------------------------------
    supabase_url: str = ""
    supabase_service_key: str = ""
    supabase_jwt_secret: str = ""

    # -- microservices ------------------------------------------------------
    llm_engine_url: str = "http://127.0.0.1:9000"

    cors_origins: list[str] = ["http://localhost:3000"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
