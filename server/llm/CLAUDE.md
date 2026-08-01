# server/llm — inference engine

OpenAI-compatible HTTP server wrapping a local MLX checkpoint. Python 3.14,
FastAPI, `mlx-lm`. Apple Silicon only (Metal).

Distribution `llm-engine`, import package `llm_engine`, a uv workspace member.
The env is the repo-root `.venv`; there is none here.

Its only client is `server/api`. It knows nothing about chats, users, or
Supabase — it takes messages and returns tokens.

## Commands

Any directory in the repo — uv finds the workspace.

```shell
uv run llm-engine                    # serve on 127.0.0.1:9000
make llm                             # same, APP_ENV=development
uv run ruff check server/llm         # lint
uv add --package llm-engine X        # add a dependency
```

First run downloads ~3.8 GB from Hugging Face. Startup is ~3 s warm.

## Endpoints

| Method | Path | Notes |
| --- | --- | --- |
| POST | `/v1/chat/completions` | `messages[]`, `stream` bool. SSE frames + `data: [DONE]` |
| GET | `/v1/models` | Single card, the loaded checkpoint |
| GET | `/health` | Liveness |

`/v1` carries `require_api_key`; `/health` does not. Errors use OpenAI's
envelope: `{"error": {"message", "type"}}`. Types: `engine_busy` (503 +
`Retry-After`), `engine_not_ready` (503), `unsupported_content` (400),
`generation_failed` (500).

## Layer map

```
__main__.py       `llm-engine` / `python -m llm_engine`. Chooses how to serve.
config.py         Settings; every knob is an LLM_* env var or .env line
app.py            create_app(settings, engine) — factory, lifespan, middleware,
                  error→status mapping. The ONLY file naming a concrete engine.
errors.py         Domain errors. Carry no HTTP vocabulary.
observability.py  Request-id contextvar + raw-ASGI middleware
engine/base.py    LLMEngine protocol, Message/Delta/Completed. Imports no framework.
engine/mlx_engine.py  Only module importing mlx
engine/prompts.py Chat templating; per-checkpoint
api/schemas.py    OpenAI wire contracts
api/deps.py       DI providers + require_api_key
api/routers/      chat.py, models.py, health.py
```

Dependency direction is strictly `api → engine`. Nothing in `engine/` may
import FastAPI.

`engine/toolcalls.py` splits a `[TOOL_CALLS]` marker out of the token stream.
It imports neither mlx nor FastAPI, which is what lets its tests run in
milliseconds without the checkpoint.

## Invariants — do not break these

- **One generation at a time.** MLX is not thread-safe. Serialization is
  enforced by `ThreadPoolExecutor(max_workers=1)`, not by the asyncio lock —
  cancelling a task does not kill its thread, so the lock alone is insufficient.
  The lock governs admission only. ([ADR 0003](../../docs/adr/0003-serialize-generation.md))
- **Weights load in lifespan, never at module import.** Module-level loading
  gives every importing process its own multi-GB copy.
- **Single process.** No `workers>1`, no `reload=True` — each would load a
  second copy of the model. `__main__.py` passes the app object, not an import
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
- **No agent logic here.** Tool loops and retrieval belong in `server/api`; a
  graph node awaiting a web search from inside this process would hold the only
  worker slot for its duration ([ADR 0006](../../docs/adr/0006-move-the-bff-into-a-python-gateway.md)).
- **Report tool calls, never execute them.** The engine parses the model's
  intent and returns it; running the tool is the gateway's job. Executing one
  here would pin the single generation worker on a network request, which is
  exactly what [ADR 0003](../../docs/adr/0003-serialize-generation.md) forbids.

## Gotchas

- **This checkpoint declares the wrong stop token.**
  `mlx-community/Mamba-Codestral-7B-v0.1-4bit` ships `config.json` with
  `eos_token_id: 0` (`<unk>`); the real EOS is `2` (`</s>`). `mlx_lm` trusts
  `config.json`, so nothing matches, the model emits a literal `</s>` as text
  and runs to `max_tokens` every time. `_reconcile_eos_tokens` in
  `engine/mlx_engine.py` unions the tokenizer's own EOS back in and warns.
  Keep it when changing checkpoints; extend via `LLM_EXTRA_EOS_TOKENS`.
  ([ADR 0004](../../docs/adr/0004-reconcile-eos-tokens.md))
- **No chat template on this tokenizer.** `prompts.py` falls back to Mistral
  `[INST]` format. No literal `<s>` — `add_bos_token=True` already emits BOS,
  and a second one puts the model off-distribution. System prompts fold into
  the first user turn; Mistral has no system role.
- **`mlx_lm.generate` is a function shadowing the module.** Use
  `importlib.import_module("mlx_lm.generate")` to introspect it.
- **`top_p=0.0` means disabled in mlx_lm**, not 1.0.
- **Tool calls work, but compliance is uneven.** The checkpoint emits proper
  Mistral `[TOOL_CALLS]` JSON — *if* `[AVAILABLE_TOOLS]` sits immediately before
  the final `[INST]`. Anywhere else and it writes the call out as Python
  instead. Measured at temperature 0: "weather in Paris" calls the tool, "who
  won the 2026 World Cup final" does not. The question matters more than the
  tool count; weather is the canonical example in Mistral's training data.
  That is a model property, not a bug to chase ([ADR 0007](../../docs/adr/0007-tool-calling-in-the-engine.md)).
- **The `[TOOL_CALLS]` marker arrives split across chunks**, like `</s>` before
  it. `engine/toolcalls.py` holds back any tail that could still become a
  marker; a plain `in` check leaks `[TOOL` into the answer.
- **`arguments` goes on the wire as a JSON string**, not an object. That is
  what OpenAI does and what langchain-openai parses; an object binds nothing
  and reports no error.
- Images are modelled end-to-end (`ImagePart`) but rejected with 400 —
  `MlxEngine.supports_images = False`. Vision means a new engine class.

## Config

`LLM_`-prefixed env vars or `server/llm/.env` / `.env.{APP_ENV}`. Full list
with defaults in `config.py`. Frequently used:

`LLM_MODEL_ID`, `LLM_PORT` (default `9000`), `LLM_API_KEYS` (JSON list; empty
disables auth), `LLM_CORS_ORIGINS`, `LLM_MAX_TOKENS_LIMIT`,
`LLM_MAX_QUEUE_DEPTH`, `LLM_EXTRA_EOS_TOKENS`.

`LLM_DEFAULT_MAX_TOKENS` is `200`, which truncates a code answer mid-block. It
applies only when the caller names no budget; the gateway sends `1024`.

**Accept both token-budget spellings.** OpenAI renamed `max_tokens` to
`max_completion_tokens`, and current clients send only the new name —
langchain-openai rewrites the old one into it unconditionally. `schemas.py`
takes either and `resolved_max_tokens` prefers the new one. Dropping the alias
puts every caller back on the 200-token default with nothing in the log.

## Testing

`server/llm/tests/` — 28 tests, ~1 s, no weights and no GPU. Run `uv run pytest`.

- `test_toolcalls.py` — the marker split at every byte boundary, malformed
  payloads, id generation.
- `test_prompts.py` — `[INST]` rendering and, above all, that the tools block
  lands immediately before the final instruction.
- `test_chat_api.py` — the OpenAI wire shape through `create_app` with a fake
  engine.

Swap in a fake engine rather than loading weights:

```python
app = create_app(settings=Settings(...), engine=FakeEngine())
```

`create_app` takes both collaborators for exactly this reason. Settings resolve
from `app.state`, not the cached global, so per-app overrides actually apply.
