<div align="center">

# ssm-mistral-mamba-chatbot

**A coding assistant powered by a state space model instead of a transformer.**

Mistral's Mamba-Codestral 7B, running locally on Apple Silicon via MLX, served
behind an OpenAI-compatible API with a Nuxt chat frontend.

<sub>

[MLX](https://github.com/ml-explore/mlx) ·
[FastAPI](https://fastapi.tiangolo.com/) ·
[Nuxt 4](https://nuxt.com/) ·
[Nuxt UI](https://ui.nuxt.com/) ·
[Vercel AI SDK](https://sdk.vercel.ai/)

</sub>

</div>

## Table of contents

- [About](#about)
- [Architecture](#architecture)
- [Features](#features)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Usage](#usage)
- [Configuration](#configuration)
- [Project structure](#project-structure)
- [Deployment](#deployment)
- [Known limitations](#known-limitations)
- [Roadmap](#roadmap)
- [License](#license)
- [Acknowledgements](#acknowledgements)

## About

Nearly every chatbot you have used is a transformer. This one is not.

**Mamba** is a state space model: it carries a fixed-size recurrent state
instead of attending over the whole context, so per-token inference cost stays
constant and there is no KV cache growing with conversation length. A
transformer's attention cost grows with context. This project exists to build
something real on that architecture and find out where the trade-off helps and
where it hurts.

The checkpoint is
[Mamba-Codestral-7B](https://huggingface.co/mistralai/Mamba-Codestral-7B-v0.1),
Mistral's code-tuned Mamba model, 4-bit quantized for MLX — so the target
domain is programming assistance.

Everything runs on your own machine. No inference leaves the device.

> **Status:** end to end. The Nuxt UI streams from the local Mamba checkpoint
> through a Python gateway — no hosted model in the path. Remaining work is the
> benchmark this project exists for. See [Roadmap](#roadmap).

## Architecture

Three processes. The frontend is a pure SPA, the gateway owns data and agent
logic, the engine owns the GPU and nothing else.

```mermaid
flowchart LR
    subgraph web["apps/web · Nuxt 4 SPA"]
        UI["Chat UI<br/>Nuxt UI 4"]
        SDK["AI SDK v7<br/>useChat"]
        UI <--> SDK
    end

    subgraph gw["server/api · FastAPI :8000"]
        R["routers/<br/>chats, auth"]
        AG["agent/<br/>LangGraph"]
        R --> AG
    end

    subgraph srv["server/llm · FastAPI :9000"]
        API["api/<br/>OpenAI schemas"]
        ENG["engine/<br/>mlx-lm"]
        API --> ENG
    end

    DB[("Supabase<br/>Postgres · Auth · pgvector")]
    GPU[["Metal GPU<br/>Mamba-Codestral 7B · 3.82 GB"]]

    SDK -- "POST /v1/chats/:id/stream" --> R
    R -. "SSE · AI SDK UI Message Stream" .-> SDK
    AG -- "POST /v1/chat/completions" --> API
    API -. "SSE · OpenAI chunks" .-> AG
    AG <--> DB
    ENG --> GPU
```

The engine implements the OpenAI chat-completions protocol deliberately: any
OpenAI client works against it by changing one base URL, and the model can be
swapped for a hosted one without touching anything above it.

Internally it is layered `api → engine`, where `engine` depends on no web
framework and `api` depends on no inference library. Pointing it at vLLM,
Ollama, or a remote endpoint means writing one class against the `LLMEngine`
protocol.

Why the gateway is a third process rather than a Nitro route — and what that
costs — is [ADR 0006](docs/adr/0006-move-the-bff-into-a-python-gateway.md).

## Features

- **Full local chat** — Nuxt UI streaming from the local checkpoint, with
  history, titles, votes, edit/regenerate and file attachments persisted in
  Postgres.
- **Agent gateway** — LangGraph graph with web-search and pgvector RAG tools
  wired in, translating between the AI SDK's UI Message Stream and the OpenAI
  protocol.
- **OpenAI-compatible API** — `/v1/chat/completions`, `/v1/models`, streaming
  and buffered, with OpenAI's error envelope.
- **Real SSE streaming** with backpressure, so a slow client throttles
  generation rather than growing an unbounded buffer.
- **Client-disconnect cancellation** — closing the tab stops the GPU work.
- **Admission control** — generation is serialized (MLX is not thread-safe);
  excess load is shed with `503` + `Retry-After` instead of queueing forever.
- **Liveness/readiness split**, so a slow model load is never mistaken for a
  dead process.
- **Optional bearer auth**, off by default for localhost, enabled by config.
- **Request-scoped logging**, so concurrent generations stay legible.
- **Multimodal-ready message schema** — image parts are modelled end to end and
  rejected with a clear 400 by text-only engines.

## Prerequisites

- **Apple Silicon Mac.** MLX targets Metal; there is no CUDA or CPU fallback.
- **~8 GB free RAM** — the 4-bit checkpoint is 3.82 GB resident.
- **~4 GB disk** for the Hugging Face cache.
- [uv](https://docs.astral.sh/uv/) for the Python half and
  [Bun](https://bun.sh/) for the frontend. uv installs the pinned Python
  (3.14) itself — no system Python needed.

## Installation

```shell
git clone <your-repo-url> ssm-mistral-mamba-chatbot
cd ssm-mistral-mamba-chatbot
make setup
```

`make setup` runs `uv sync` and `bun install`. The Python side is a uv
workspace: one `.venv` at the repo root shared by every member, resolved from
the committed `uv.lock`.

Both halves need env files. A Supabase project supplies the database, auth and
storage; the anon key goes to the browser and the service-role key never
leaves the gateway.

```shell
cp .env.example server/api/.env.development
cp apps/web/.env.example apps/web/.env.development
```

Then apply the migrations in [`supabase/migrations/`](supabase/migrations/) to
your project.

## Usage

Three processes, three terminals. Start the engine first — the first run
downloads the checkpoint (~3.8 GB); later starts take a few seconds.

```shell
make llm          # inference engine  :9000
make api          # gateway           :8000
make web          # chat UI           :3000  → http://localhost:3000
```

The engine is usable on its own with any OpenAI client:

```shell
curl -N http://127.0.0.1:9000/v1/chat/completions \
  -H 'content-type: application/json' \
  -d '{
        "messages": [{"role": "user", "content": "Write a Python LRU cache."}],
        "stream": true
      }'
```

```python
from openai import OpenAI

client = OpenAI(base_url="http://127.0.0.1:9000/v1", api_key="not-needed")
stream = client.chat.completions.create(
    model="mamba-codestral",
    messages=[{"role": "user", "content": "Explain state space models."}],
    stream=True,
)
for chunk in stream:
    print(chunk.choices[0].delta.content or "", end="", flush=True)
```

### Endpoints

`server/llm` — the OpenAI-compatible engine:

| Method | Path | Description |
| --- | --- | --- |
| `POST` | `/v1/chat/completions` | Chat, buffered or SSE (`"stream": true`) |
| `GET` | `/v1/models` | Lists the loaded checkpoint |
| `GET` | `/health` | Liveness |

`server/api` — the gateway the browser talks to, bearer-authenticated with a
Supabase JWT:

| Method | Path | Description |
| --- | --- | --- |
| `POST` | `/v1/chats/{id}/stream` | A chat turn, as an AI SDK UI Message Stream |
| `GET`/`POST` | `/v1/chats` | List and create chats |
| `GET`/`DELETE` | `/v1/chats/{id}` | Fetch with messages; delete |
| `PATCH` | `/v1/chats/{id}/title`, `/visibility` | |
| `GET`/`POST` | `/v1/chats/{id}/votes` | |
| `GET` | `/v1/models` | Checkpoints the engine has loaded, for the UI picker |
| `GET` | `/health` | Liveness |

## Configuration

Both Python services read `LLM_`-prefixed environment variables from
`server/<half>/.env` or `.env.{APP_ENV}`, where `APP_ENV` is `development`,
`staging`, or `production`. Defaults live in each half's `config.py`.

`server/llm` — [`config.py`](server/llm/llm_engine/config.py):

| Variable | Default | Description |
| --- | --- | --- |
| `LLM_MODEL_ID` | `mlx-community/Mamba-Codestral-7B-v0.1-4bit` | Any MLX checkpoint |
| `LLM_HOST` / `LLM_PORT` | `127.0.0.1` / `9000` | Bind address |
| `LLM_API_KEYS` | `[]` | JSON list; empty disables auth |
| `LLM_CORS_ORIGINS` | `["http://localhost:3000", "http://127.0.0.1:8000"]` | Allowed origins |
| `LLM_TEMPERATURE` | `0.7` | Sampling default; per-request override allowed |
| `LLM_DEFAULT_MAX_TOKENS` | `200` | Per-reply default — raise it for long answers |
| `LLM_MAX_TOKENS_LIMIT` | `2048` | Hard server-side ceiling |
| `LLM_MAX_QUEUE_DEPTH` | `8` | Waiting requests before shedding load |
| `LLM_EXTRA_EOS_TOKENS` | `[]` | Extra stop tokens for other checkpoints |

`server/api` — [`config.py`](server/api/app/core/config.py):

| Variable | Default | Description |
| --- | --- | --- |
| `APP_ENV` | `development` | Selects the env file; also relaxes auth |
| `LLM_HOST` / `LLM_PORT` | `127.0.0.1` / `8000` | Bind address |
| `LLM_LLM_ENGINE_URL` | `http://127.0.0.1:9000` | Where `server/llm` listens |
| `LLM_SUPABASE_URL` | — | Project URL |
| `LLM_SUPABASE_SERVICE_KEY` | — | Service-role key. Never ships to the browser |
| `LLM_SUPABASE_JWT_SECRET` | — | Verifies incoming bearer tokens |
| `LLM_MAX_TOKENS` | `1024` | Budget sent per reply; the engine's own default is 200 |
| `LLM_CORS_ORIGINS` | `["http://localhost:3000", "http://127.0.0.1:3000"]` | Must list the SPA's origin |

The doubled `LLM_LLM_ENGINE_URL` is not a typo: the prefix is `LLM_` and the
setting is `llm_engine_url`.

```shell
LLM_MODEL_ID=mlx-community/Qwen2.5-7B-Instruct-4bit uv run llm-engine
```

Frontend configuration lives in `apps/web/.env.development` — see
`.env.example`.

> **`APP_ENV=development` disables authentication** on the gateway: requests
> without a token resolve to a fixed dev user and chats are not filtered by
> owner. Never point a development gateway at production data.

## Project structure

```
pyproject.toml           uv workspace root — no package of its own
uv.lock                  Committed; one lock for every Python member
Makefile                 Single entrypoint across both package managers
server/
  llm/                   Inference engine — distribution "llm-engine"
    llm_engine/
      __main__.py        Entrypoint behind the `llm-engine` script
      config.py          Env-driven settings
      app.py             App factory: lifespan, middleware, error mapping
      errors.py          Domain errors, decoupled from HTTP
      observability.py   Request-id logging
      engine/            Model runtimes (base.py defines the protocol)
      api/               Schemas, dependencies, routers
  api/                   BFF gateway — distribution "api-server"
    app/
      main.py            FastAPI app, CORS, routers
      core/              Settings and JWT verification
      routers/           /v1/chats — CRUD plus the streaming turn
      services/          Supabase client, chat persistence
      agent/             LangGraph graph, tools, AI SDK stream adapter
apps/
  web/                   Nuxt 4 chat frontend — bun, own lockfile
supabase/migrations/     Schema, RLS, pgvector
packages/                Future Python members (benchmarks)
```

## Deployment

Split three ways, and none of it is Docker.

| Piece | Where | How |
| --- | --- | --- |
| `apps/web` | Vercel | Nitro's `vercel` preset, no code changes — [ADR 0002](docs/adr/0002-host-the-frontend-on-vercel.md) |
| `server/api` | Any host with a persistent process | Holds the service-role key — [ADR 0006](docs/adr/0006-move-the-bff-into-a-python-gateway.md) |
| `server/llm` | Natively, on a Mac | `uv run llm-engine`, reached over a tunnel — [ADR 0001](docs/adr/0001-run-the-server-natively.md) |

The reasoning and the rejected alternatives live in
[`docs/adr/`](docs/adr/README.md).

## Known limitations

- **Apple Silicon only.** MLX has no CUDA or CPU backend, and the server cannot
  be containerized — [ADR 0001](docs/adr/0001-run-the-server-natively.md).
- **One generation at a time.** Excess load is shed with `503`, not queued —
  [ADR 0003](docs/adr/0003-serialize-generation.md).
- **Tool calling is implemented but unevenly obeyed.** The engine speaks
  Mistral's `[TOOL_CALLS]` protocol and the checkpoint does use it — for
  questions close to its training distribution. Others get answered in prose
  instead. A tool-tuned checkpoint works unchanged —
  [ADR 0007](docs/adr/0007-tool-calling-in-the-engine.md).
- **Output quality is bounded by a 4-bit base checkpoint.** Codestral Mamba is
  not instruction-tuned, so it paraphrases prompts back, and quantization
  occasionally emits a stray non-ASCII token mid-identifier.
- **Text only.** The schema models image parts; no vision engine exists yet.
- **This checkpoint ships a wrong stop token**, and the engine corrects it at
  load — [ADR 0004](docs/adr/0004-reconcile-eos-tokens.md).

## Roadmap

- [x] OpenAI-compatible streaming inference server
- [x] Admission control, cancellation, readiness probes
- [x] uv workspace, committed lockfile, CI on both halves
- [x] Point the Nuxt frontend at the local model instead of hosted ones
- [x] Supabase-backed persistence, auth, and a LangGraph agent gateway
- [ ] Replace the placeholder model registry with what the deployment serves
- [ ] Coding-focused system prompt in place of the template's generic persona
- [ ] Benchmark Mamba vs. a comparable transformer on latency, memory, and
      long-context behaviour — the experiment this project exists for
- [x] Tool calling end to end — engine protocol, gateway execution
- [ ] Automated test suite — `server/llm` covered; `server/api` still has none
- [ ] Deploy the frontend (Vercel), host the gateway, tunnel to the engine

## License

MIT — see [LICENSE](LICENSE).

> The current `LICENSE` still carries the Nuxt UI Templates copyright line
> inherited from the frontend template. Update the holder before publishing.

## Acknowledgements

- [Mistral AI](https://mistral.ai/) — Codestral Mamba
- [Albert Gu and Tri Dao](https://arxiv.org/abs/2312.00752) — the Mamba
  architecture
- [Apple MLX](https://github.com/ml-explore/mlx) and
  [`mlx-lm`](https://github.com/ml-explore/mlx-lm)
- [`mlx-community`](https://huggingface.co/mlx-community) — quantized weights
- [Nuxt UI chat template](https://github.com/nuxt-ui-templates/chat) — frontend
  starting point
