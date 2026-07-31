import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

app_env = os.getenv("APP_ENV", "development")
BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    app_env: str = app_env
    model_config = SettingsConfigDict(
        env_prefix="LLM_",
        env_file=(
            str(BASE_DIR / ".env"),
            str(BASE_DIR / f".env.{app_env}"),
            ".env",
            f".env.{app_env}",
        ),
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
    model_id: str = "mlx-community/Mamba-Codestral-7B-v0.1-4bit"
    # The engine defaults to 200, which truncates a code answer mid-block. Ask
    # for a usable budget explicitly rather than moving the engine's default,
    # which other clients depend on. Must stay under LLM_MAX_TOKENS_LIMIT.
    max_tokens: int = 1024

    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
