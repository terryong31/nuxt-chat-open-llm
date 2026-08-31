import gc
from typing import Optional, Any
from mlx_lm import load
import mlx.core as mx
from local_llm.core.config import settings


class ModelManager:
    """
    Unified Memory Model Manager with On-Demand Dynamic Swap.
    - Loads the default model at startup to keep memory footprint lean (< 10GB).
    - When switching models via API, unloads the active model, runs GC, clears Metal cache, and loads the new model.
    - Flushes all memory and cache on shutdown.
    """
    model: Any = None
    tokenizer: Any = None
    model_id: Optional[str] = None

    @classmethod
    def preload_default_model(cls) -> None:
        """
        Preloads the default model at startup to keep memory footprint healthy.
        """
        target = settings.DEFAULT_MODEL
        print(f"🚀 Preloading default model ({target}) into Unified Memory...")
        try:
            cls.activate_model(target)
            print(f"✨ Default model {target} active and ready!")
        except Exception as e:
            print(f"⚠️ Failed to preload default model {target}: {e}")

    @classmethod
    def preload_all_models(cls) -> None:
        """Alias for startup preloading."""
        cls.preload_default_model()

    @classmethod
    def activate_model(cls, model_id: str) -> None:
        """
        Activates the requested model on-demand.
        If already active, returns immediately.
        If switching to a new model, releases previous model memory first.
        """
        if not model_id:
            model_id = settings.DEFAULT_MODEL

        # Already active in memory
        if cls.model_id == model_id and cls.model is not None:
            return

        print(f"🔄 Switching model from '{cls.model_id}' to '{model_id}'...")

        # 1. Unload previous model & clear GPU/Metal memory
        if cls.model is not None:
            print(f"🧹 Unloading previous model '{cls.model_id}' to free Unified Memory...")
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

        # 2. Load the requested model
        print(f"🚀 Loading {model_id} into Unified Memory...")
        try:
            m, t, *_ = load(model_id)
            cls.model = m
            cls.tokenizer = t
            cls.model_id = model_id
            print(f"✓ Model {model_id} loaded & active!")
        except Exception as e:
            print(f"⚠️ Failed to load {model_id}: {e}")
            if model_id != settings.DEFAULT_MODEL:
                print(f"↩️ Falling back to default model: {settings.DEFAULT_MODEL}")
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
        Flushes all models from Unified Memory and clears MLX Metal cache.
        """
        print("🧹 Flushing MLX model from Unified Memory...")
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
        print("✓ Unified Memory and MLX Metal cache fully flushed!")
