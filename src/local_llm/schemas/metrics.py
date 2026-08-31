from pydantic import BaseModel


class MetricsResponse(BaseModel):
    """Hardware & generation telemetry metrics."""
    total_tokens: int
    thinking_tokens: int
    answer_tokens: int
    generation_tps: float
    elapsed_time_sec: float
    prompt_tokens: int
    prompt_tps: float
    peak_memory_gb: float
