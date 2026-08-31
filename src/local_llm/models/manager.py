import gc
from typing import Optional, Dict, Tuple, Any
from mlx_lm import load
import mlx.core as mx
from local_llm.core.config import settings


class ModelManager:
    """
    Unified Memory Model Manager.
    - Preloads all configured models into Unified Memory at startup.
    - Switches between models with 0.0s delay (in-memory pointer swap).
    - Flushes all models and Metal cache on shutdown.
    """
    _loaded_models: Dict[str, Tuple[Any, Any]] = {}
    model: Any = None
    tokenizer: Any = None
    model_id: Optional[str] = settings.DEFAULT_MODEL

    @classmethod
    def preload_all_models(cls) -> None:
        """
        Preloads all supported models into Unified Memory at application startup.
        """
        print("🚀 Preloading all local MLX models into Unified Memory...")
        for mid in settings.SUPPORTED_MODELS:
            if mid not in cls._loaded_models:
                print(f"📦 Preloading {mid} ...")
                try:
                    m, t, *_ = load(mid)
                    cls._loaded_models[mid] = (m, t)
                    print(f"✓ Model {mid} preloaded & cached!")
                except Exception as e:
                    print(f"⚠️ Failed to preload {mid}: {e}")

        # Set default active model
        if settings.DEFAULT_MODEL in cls._loaded_models:
            cls.activate_model(settings.DEFAULT_MODEL)
        elif cls._loaded_models:
            first_mid = next(iter(cls._loaded_models))
            cls.activate_model(first_mid)
        print(f"✨ Models in memory: {list(cls._loaded_models.keys())} | Active default: {cls.model_id}")

    @classmethod
    def activate_model(cls, model_id: str) -> None:
        """
        Activates the requested model when called via API.
        If already in cache, activation is instantaneous (0.0s delay).
        """
        if model_id in cls._loaded_models:
            if cls.model_id != model_id or cls.model is None:
                cls.model, cls.tokenizer = cls._loaded_models[model_id]
                cls.model_id = model_id
                print(f"⚡ Activated model: {model_id} (instant memory switch)")
        else:
            print(f"🚀 Model {model_id} not in cache, loading on-demand...")
            try:
                m, t, *_ = load(model_id)
                cls._loaded_models[model_id] = (m, t)
                cls.model, cls.tokenizer = m, t
                cls.model_id = model_id
                print(f"✓ Model {model_id} loaded & cached!")
            except Exception as e:
                print(f"⚠️ Failed to load {model_id}, falling back to default: {e}")
                if settings.DEFAULT_MODEL in cls._loaded_models:
                    cls.activate_model(settings.DEFAULT_MODEL)

    @classmethod
    def load_model(cls, model_id: str = settings.DEFAULT_MODEL) -> None:
        """Legacy alias pointing to activate_model."""
        cls.activate_model(model_id)

    @classmethod
    def unload_model(cls) -> None:
        """Legacy alias pointing to unload_all."""
        cls.unload_all()

    @classmethod
    def unload_all(cls) -> None:
        """
        Flushes all models from Unified Memory and clears MLX cache on shutdown.
        """
        print("🧹 Flushing all MLX models from Unified Memory...")
        cls._loaded_models.clear()
        cls.model = None
        cls.tokenizer = None
        cls.model_id = None
        gc.collect()
        try:
            if hasattr(mx, "clear_cache"):
                mx.clear_cache()
            elif hasattr(mx, "metal") and hasattr(mx.metal, "clear_cache"):
                mx.metal.clear_cache()
        except Exception:
            pass
        print("✓ All Unified Memory and MLX cache fully flushed!")
