"""Environment-driven configuration.

Every knob that used to be a module constant lives here, so the same build can
be pointed at a different checkpoint or tuned for a smaller box without a code
change. Every field reads from a `LLM_`-prefixed env var or a `.env` file:

    LLM_MODEL_ID=mlx-community/Qwen2.5-7B-Instruct-4bit LLM_PORT=9000 python main.py
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="LLM_",
        env_file=".env",
        extra="ignore",
        # pydantic reserves the `model_` prefix for its own attributes. These
        # are "model" in the ML sense, not the pydantic sense.
        protected_namespaces=(),
    )

    # -- server -------------------------------------------------------------
    host: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "INFO"

    # Browsers refuse cross-origin XHR unless the server opts in, and the Nuxt
    # dev server is a different origin from this API.
    cors_origins: list[str] = ["http://localhost:3000"]

    # Empty means auth is off, which is the right default for a server bound to
    # localhost. Setting it turns on the `require_api_key` dependency that is
    # already attached to the /v1 router.
    api_keys: list[str] = []

    # -- model --------------------------------------------------------------
    model_id: str = "mlx-community/Mamba-Codestral-7B-v0.1-4bit"
    # MLX keeps freed GPU buffers in a reusable pool that is unbounded by
    # default. Capping it hands memory back to the OS between requests instead
    # of holding it for the lifetime of the process.
    cache_limit_mb: int = 512
    # Extra strings to treat as end-of-turn, on top of the checkpoint's own.
    # Needed for models whose stop tokens are not declared in their config,
    # e.g. ["<|im_end|>"] for some ChatML conversions.
    extra_eos_tokens: list[str] = []

    # -- sampling defaults (a request may override the first three) ----------
    temperature: float = 0.7
    # 0.0 disables top-p in mlx_lm; it is not the same as 1.0 in every sampler,
    # so the "off" value is spelled explicitly rather than assumed.
    top_p: float = 0.0
    repetition_penalty: float = 1.1
    repetition_context_size: int = 10
    default_max_tokens: int = 200
    # A hard ceiling on how long one client can keep the GPU busy. Requests
    # asking for more are clamped, not rejected.
    max_tokens_limit: int = 2048

    # -- admission control --------------------------------------------------
    # Generation is serialized, so without a bound a burst just grows an
    # unbounded queue of clients that have long since given up waiting.
    max_queue_depth: int = 8
    queue_timeout_s: float = 60.0
    # Tokens buffered between the generating thread and the HTTP response.
    # Small on purpose: a slow client should throttle generation, not cause an
    # unbounded buffer to grow behind it.
    stream_queue_size: int = 64


@lru_cache
def get_settings() -> Settings:
    """Cached so the env is read once and every layer sees the same object."""
    return Settings()
