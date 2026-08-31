from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List


class Settings(BaseSettings):
    """
    Centralized Application Configuration.
    Loads settings from environment variables or .env file with defaults.
    """
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Server Configuration
    PROJECT_NAME: str = "Local MLX LLM API"
    PROJECT_DESCRIPTION: str = "High-performance Apple Silicon Local LLM API using FastAPI & MLX"
    VERSION: str = "1.0.0"
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    RELOAD: bool = False

    # CORS Settings
    CORS_ORIGINS: List[str] = ["*"]

    # LLM Defaults
    DEFAULT_MODEL: str = "mlx-community/Qwen3.5-9B-MLX-8bit"
    SUPPORTED_MODELS: List[str] = [
        "mlx-community/Qwen3.5-9B-MLX-8bit",
        "mlx-community/Qwen3.8-27B-4bit",
    ]
    DEFAULT_TEMPERATURE: float = 0.7
    DEFAULT_TOP_P: float = 0.9
    DEFAULT_MAX_TOKENS: int = 2048
    DEFAULT_THINKING_BUDGET: int = 100

    # Hugging Face Configuration
    HF_TOKEN: str = ""


settings = Settings()
