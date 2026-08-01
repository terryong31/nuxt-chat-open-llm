# server/api — BFF gateway

The browser's only backend. Verifies Supabase JWTs, owns chat persistence, runs
the LangGraph agent, and forwards generation to `server/llm`. Python 3.14,
FastAPI, LangGraph, `supabase-py`.

Distribution `api-server`, import package `app`, a uv workspace member. The env
is the repo-root `.venv`; there is none here.

```shell
uv run api-server                 # :8000, any directory in the repo
make api                          # same, with APP_ENV=development
uv add --package api-server X
```

Needs `server/llm` running on `:9000` and reachable Supabase credentials.

## Layer map

```
main.py             FastAPI app, CORS, router mounting
core/config.py      LLM_-prefixed settings; env file per APP_ENV
core/security.py    get_current_user — JWT verification, env-dependent
routers/chats.py    /v1/chats CRUD + the streaming turn
routers/health.py   GET /health
services/supabase.py   Admin client (service-role key) singleton
services/chat_service.py  Every table write lives here
services/llm_client.py    Direct OpenAI-protocol client. Unused by the agent
                          path; kept as the no-LangGraph fallback
agent/graph.py      load_history → call_llm ⇄ run_tools → save_reply
                    → generate_title
agent/state.py      AgentState TypedDict
agent/stream.py     LangGraph events → AI SDK UI Message Stream
agent/tools/        web_search, rag_search
```

## Endpoints

All under `/v1/chats`, all requiring `Authorization: Bearer <supabase-jwt>`
outside development.

| Method | Path | Notes |
| --- | --- | --- |
| GET/POST | `` | List; create chat with its first message |
| GET/DELETE | `/{id}` | Fetch with messages; delete chat + its storage folder |
| PATCH | `/{id}/title`, `/{id}/visibility` | |
| GET/POST | `/{id}/votes` | |
| DELETE | `/{id}/messages` | Truncate from a message — `type: "edit" \| "regenerate"` |
| POST | `/{id}/stream` | The turn. SSE, see below |

## Invariants — do not break these

- **`/stream` speaks the AI SDK UI Message Stream, not the OpenAI protocol.**
  `ai@7` consumes SSE frames of JSON chunk objects — `text-start`, `text-delta`,
  `text-end`, wrapped in `start`/`finish`, terminated by `data: [DONE]`. The
  `0:"token"` framing in the SDK's v3/v4 docs is retired. Response headers must
  be `content-type: text/event-stream` and `x-vercel-ai-ui-message-stream: v1`.
- **A `text-delta` needs an open `text-start` with the same `id`.** Deltas for
  an unopened id are dropped with a console warning and render as nothing. Open
  the part lazily on the first non-empty delta, and close it on *every* exit
  path including the error path — `agent/stream.py` does both.
- **This layer fails silently at the browser.** A malformed stream produces no
  server error, no HTTP error, and no client exception — just an empty message.
  Curl the endpoint and read the frames; do not debug it from the UI.
- **The DB is the conversation, not the request body.** The client POSTs its
  whole transcript, but `stream_chat` persists only the incoming user turn and
  `load_history` reads everything back from Postgres. Seeding the graph from
  the payload *and* the DB double-feeds the prompt.
- **The assistant message id is minted before generation** and used in three
  places: the `start` frame, the persisted row, and therefore every later vote
  or edit. A client-side id would reference a row that does not exist.
- **Chat titles come from the same local model, tagged and filtered.**
  `generate_title` reuses the engine rather than adding a second model, so its
  tokens arrive on the same `on_chat_model_stream` channel as the answer. The
  run is tagged `chat-title` and `agent/stream.py` drops anything carrying that
  tag — without the filter the title is appended to the visible reply. The
  finished title reaches the client as a **transient** `data-chat-title` part,
  transient because it belongs to the chat, not to the message.
- **Title generation runs last, never alongside the answer.** The engine
  serializes generation onto one worker ([ADR 0003](../../docs/adr/0003-serialize-generation.md)),
  so a concurrent title call would queue ahead of the reply or be shed as load.
  It also only runs when the title is still empty, so a hand-typed name
  survives every later turn.
- **Mid-stream writes degrade, they do not raise.** `ChatService.save_message`
  returns `None` on failure so a DB hiccup costs history, not the response the
  user is waiting on. Callers must handle `None` — `stream_chat` falls back to
  seeding the turn in memory. The trade-off is real: this is what let a
  systematic id-type failure drop every user turn while the UI looked fine.
  Read the log, not the screen, when history goes missing.
- **Client message ids are coerced to UUIDs** (`_as_uuid`). `messages.id` is a
  `uuid` column; the AI SDK's default generator emits nanoid strings, which
  Postgres rejects outright. The client is configured to mint UUIDs, and this
  is the backstop that keeps a client change from costing history again.
- **Ask the engine for a token budget explicitly.** `LLM_MAX_TOKENS` (default
  1024) is passed on every call. The engine's own default is 200, which cuts a
  code answer off mid-block. Note that langchain-openai always serialises the
  budget as `max_completion_tokens`, never `max_tokens` — the engine accepts
  both spellings, and it silently ignored the request until it did.

## Gotchas

- **Development mode is not authenticated.** `get_current_user` returns a fixed
  `DEV_USER` with no credentials and decodes JWTs without verifying signatures;
  `ChatService` also skips `user_id` filtering when `APP_ENV=development`, so
  every chat is visible to everyone. Staging and production verify properly.
  Never point a development gateway at a real Supabase project.
- **CORS is load bearing.** The browser calls this service cross-origin. If
  `LLM_CORS_ORIGINS` omits the SPA's origin, chat fails with nothing in the
  server log.
- **The engine URL variable is doubled.** `env_prefix` is `LLM_`, so the
  setting `llm_engine_url` reads `LLM_LLM_ENGINE_URL`. Likewise Supabase is
  `LLM_SUPABASE_URL`, `LLM_SUPABASE_SERVICE_KEY`, `LLM_SUPABASE_JWT_SECRET`.
- **`get_settings` is `lru_cache`d and `_cached_llm` caches per model id.**
  Changing an env var needs a restart, not a reload.
- **Tools now reach the model, but it does not always use them.** The engine
  implements Mistral's tool protocol ([ADR 0007](../../docs/adr/0007-tool-calling-in-the-engine.md)),
  so `run_tools` is live. Compliance depends on the question, not on the tool
  count — expect `should_use_tools` to route to `save_reply` more often than a
  hosted model would.
- **The system prompt is folded into the first user turn** by the engine's
  Mistral formatting, so it is charged to the user's own message. Keep it
  short; that is why it is not a page of persona.

## Config

`LLM_`-prefixed env vars, or `server/api/.env` / `.env.{APP_ENV}`. Full list in
`core/config.py`. `APP_ENV` itself is unprefixed and selects the env file.

| Variable | Default |
| --- | --- |
| `APP_ENV` | `development` |
| `LLM_HOST` / `LLM_PORT` | `127.0.0.1` / `8000` |
| `LLM_LLM_ENGINE_URL` | `http://127.0.0.1:9000` |
| `LLM_SUPABASE_URL` / `_SERVICE_KEY` / `_JWT_SECRET` | empty |
| `LLM_CORS_ORIGINS` | `["http://localhost:3000", "http://127.0.0.1:3000"]` |
| `LLM_MODEL_ID` | `mlx-community/Mamba-Codestral-7B-v0.1-4bit` |
| `LLM_MAX_TOKENS` | `1024` (must stay under the engine's `LLM_MAX_TOKENS_LIMIT`) |

## Testing

No suite committed. `pyproject.toml` points `testpaths` at `server/api/tests`,
which does not exist yet — `pytest` currently collects nothing and still exits
zero, so a green run here means nothing.

The stream adapter is the piece worth testing first and the easiest to test:
it is a pure async generator over an event iterator, so it needs no model, no
database, and no HTTP.
