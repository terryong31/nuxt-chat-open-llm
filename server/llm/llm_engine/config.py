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
    port: int = 9000
    log_level: str = "INFO"

    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:8000"]
    api_keys: list[str] = []

    # -- model --------------------------------------------------------------
    model_id: str = "mlx-community/Mamba-Codestral-7B-v0.1-4bit"
    cache_limit_mb: int = 512
    extra_eos_tokens: list[str] = []

    # -- sampling defaults --------------------------------------------------
    temperature: float = 0.7
    top_p: float = 0.0
    repetition_penalty: float = 1.1
    repetition_context_size: int = 10
    default_max_tokens: int = 200
    max_tokens_limit: int = 2048

    # -- admission control --------------------------------------------------
    max_queue_depth: int = 8
    queue_timeout_s: float = 60.0
    stream_queue_size: int = 64


@lru_cache
def get_settings() -> Settings:
    return Settings()
