# 0003 — Serialize generation, shed excess load

Accepted · 2026-08-01

## Context

- MLX is not thread-safe.
- One 7B model on one GPU gains nothing from interleaving requests.
- Exposed over a tunnel, the server can receive arbitrary concurrency.

## Decision

One generation at a time, enforced by `ThreadPoolExecutor(max_workers=1)`.
Admission control is a lock plus a queue-depth counter; past
`LLM_MAX_QUEUE_DEPTH` requests are rejected with `503` + `Retry-After` rather
than queued.

## Rejected

| Option | Why not |
| --- | --- |
| Unbounded queue | Latency grows without bound and a client cannot tell slow from stuck |
| `workers > 1` | N copies of a 3.8 GB model on one GPU |
| Continuous batching | `mlx_lm.stream_generate` is single-sequence. This is vLLM's job, not MLX's |

## Consequences

- Throughput ceiling is one stream. Scale means more machines behind a proxy,
  never more workers in front of one GPU.
- **The executor is the guarantee, not the asyncio lock.** Cancelling a task
  does not kill its thread, so the lock alone would not serialize anything. It
  governs admission only.
- Cancellation has to be real: `emit()` polls the cancel flag instead of
  blocking, or one disconnected client pins the only worker forever.
- `main.py` passes the app object rather than an import string so `--workers`
  and `--reload` are unreachable by construction. `asgi.py` exists for process
  managers that need a string and reopens that door — deliberately, and noted.
