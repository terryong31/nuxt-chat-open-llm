# server — inference API

OpenAI-compatible HTTP server wrapping a local MLX checkpoint. Python 3.14,
FastAPI, `mlx-lm`. Apple Silicon only (Metal).

## Commands

Run from `server/`. Always use the venv interpreter — there is no global install.

```shell
.venv/bin/python main.py                 # serve on 127.0.0.1:8000
.venv/bin/python test.py                 # streaming REPL client
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m pyflakes llm_server  # lint
```

First run downloads ~3.8 GB from Hugging Face. Startup is ~3 s warm.

## Endpoints

| Method | Path | Notes |
| --- | --- | --- |
| POST | `/v1/chat/completions` | `messages[]`, `stream` bool. SSE frames + `data: [DONE]` |
| GET | `/v1/models` | Single card, the loaded checkpoint |
| GET | `/healthz` | Liveness. 200 even during warm-up |
| GET | `/readyz` | Readiness. 503 until weights resident |

Errors use OpenAI's envelope: `{"error": {"message", "type"}}`. Types:
`engine_busy` (503 + `Retry-After`), `engine_not_ready` (503),
`unsupported_content` (400), `generation_failed` (500).

## Layer map

```
config.py         Settings; every knob is an LLM_* env var or .env line
app.py            create_app(settings, engine) — factory, lifespan, middleware,
                  error→status mapping. The ONLY file naming a concrete engine.
errors.py         Domain errors. Carry no HTTP vocabulary.
observability.py  Request-id contextvar + raw-ASGI middleware
engine/base.py    LLMEngine protocol, Message/Delta/Completed. Imports no framework.
engine/mlx_engine.py  Only module importing mlx
engine/prompts.py Chat templating; per-checkpoint
services/chat.py  Orchestration seam. Sampling policy, content rejection.
api/schemas.py    OpenAI wire contracts
api/deps.py       DI providers + require_api_key
api/routers/      chat.py, models.py, health.py
```

Dependency direction is strictly `api → services → engine`. Nothing in
`engine/` or `services/` may import FastAPI.

## Invariants — do not break these

- **One generation at a time.** MLX is not thread-safe. Serialization is
  enforced by `ThreadPoolExecutor(max_workers=1)`, not by the asyncio lock —
  cancelling a task does not kill its thread, so the lock alone is insufficient.
  The lock governs admission only.
- **Weights load in lifespan, never at module import.** Module-level loading
  gives every importing process its own multi-GB copy.
- **Single process.** No `workers>1`, no `reload=True` — each would load a
  second copy of the model. `main.py` passes the app object, not an import
  string, to make this impossible by construction.
- **Pull the first stream event inside the route before returning
  `StreamingResponse`.** Once SSE headers are sent the status code is fixed, so
  admission/readiness errors must surface before that.
- **Never yield inside the SSE generator's `finally`.** Awaiting there is legal
  during close; yielding raises. `data: [DONE]` lives in the `else` branch.
- **Bounded queue between worker and response.** Backpressure is deliberate: a
  slow client must throttle generation, not grow a buffer.
- **`emit()` polls `cancel` rather than blocking outright.** A disconnected
  client would otherwise pin the only worker thread forever.

## Gotchas

- **This checkpoint declares the wrong stop token.**
  `mlx-community/Mamba-Codestral-7B-v0.1-4bit` ships `config.json` with
  `eos_token_id: 0` (`<unk>`); the real EOS is `2` (`</s>`). `mlx_lm` trusts
  `config.json`, so nothing matches, the model emits a literal `</s>` as text
  and runs to `max_tokens` every time. `_reconcile_eos_tokens` in
  `engine/mlx_engine.py` unions the tokenizer's own EOS back in and warns.
  Keep it when changing checkpoints; extend via `LLM_EXTRA_EOS_TOKENS`.
- **No chat template on this tokenizer.** `prompts.py` falls back to Mistral
  `[INST]` format. No literal `<s>` — `add_bos_token=True` already emits BOS,
  and a second one puts the model off-distribution. System prompts fold into
  the first user turn; Mistral has no system role.
- **`mlx_lm.generate` is a function shadowing the module.** Use
  `importlib.import_module("mlx_lm.generate")` to introspect it.
- **`top_p=0.0` means disabled in mlx_lm**, not 1.0.
- Images are modelled end-to-end (`ImagePart`) but rejected with 400 —
  `MlxEngine.supports_images = False`. Vision means a new engine class.

## Config

`LLM_`-prefixed env vars or `server/.env`. Full list with defaults in
`config.py`. Frequently used:

`LLM_MODEL_ID`, `LLM_PORT`, `LLM_API_KEYS` (JSON list; empty disables auth),
`LLM_CORS_ORIGINS`, `LLM_MAX_TOKENS_LIMIT`, `LLM_MAX_QUEUE_DEPTH`,
`LLM_EXTRA_EOS_TOKENS`.

## Testing

No test suite committed yet. Swap in a fake engine rather than loading weights:

```python
app = create_app(settings=Settings(...), engine=FakeEngine())
```

`create_app` takes both collaborators for exactly this reason. Settings resolve
from `app.state`, not the cached global, so per-app overrides actually apply.
