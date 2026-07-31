# 0006 — Move the BFF out of Nitro into a Python gateway

Accepted · 2026-08-01

## Context

The frontend arrived from the template with a full backend attached: Nitro
routes under `apps/web/server/`, `hub:db` (SQLite locally, Turso in prod) via
Drizzle, `nuxt-auth-utils` for GitHub OAuth, and `streamText` calling hosted
models through the Vercel AI Gateway. The inference server was a fourth thing
nothing talked to — [0005](0005-render-the-frontend-client-side.md) recorded
that "wiring it is the central open task."

[0005](0005-render-the-frontend-client-side.md) also looked at whether that
Nitro layer could dissolve into composables, and said no: of 14 server files,
12 imported `hub:db` and 13 read the session. Moving them into the browser
would ship the database token, the GitHub secret, and the cookie seal with the
bundle. That reasoning was sound but assumed the only two places code can run
are Nitro and the browser.

Two requirements broke that assumption. The agent loop wanted LangGraph, and
retrieval wanted pgvector — both Python, neither reachable from a TypeScript
Nitro route without a second service anyway. Once a Python service has to exist
to hold the agent, the question stops being "Nitro or browser" and becomes
"which server owns the data."

## Decision

Three processes, each with one job:

| Process | Port | Owns |
| --- | --- | --- |
| `apps/web` | 3000 | SPA. Rendering only; no `server/` directory. |
| `server/api` | 8000 | Agent graph, persistence, auth verification. |
| `server/llm` | 9000 | Model weights and generation. Nothing else. |

Supabase replaces `hub:db` + Drizzle + `nuxt-auth-utils` — Postgres, Auth,
Storage, and pgvector behind one credential. The browser holds a Supabase
session JWT and sends it as a bearer token; `server/api` verifies it and is the
only holder of the service-role key.

The engine stays exactly as [0001](0001-run-the-server-natively.md) and
[0003](0003-serialize-generation.md) describe it. It gained a neighbour, not a
responsibility.

## Rejected

| Option | Why not |
| --- | --- |
| Keep the Nitro BFF, call the engine from it | The agent loop and RAG are Python. A Python service has to exist regardless; this keeps a second backend alive to forward requests to it |
| Put the agent graph inside `server/llm` | [0003](0003-serialize-generation.md) serializes generation onto one worker thread. A graph node awaiting a web search would hold the GPU slot for the duration, and it inverts the `api → services → engine` direction that ADR's guarantees rest on |
| Browser talks to Supabase directly, RLS for safety | Agent writes and RAG ingestion need the service-role key, which cannot go in a bundle. It also puts the agent loop on the client, where a closed tab abandons a half-written turn |
| Keep `hub:db`, add pgvector alongside | Two databases, two auth stories, and chat history that cannot join against embeddings |

## Consequences

- **The browser now makes cross-origin requests.** CORS on the gateway is load
  bearing, not hygiene — `LLM_CORS_ORIGINS` must list the SPA's origin or every
  chat fails with no server-side error to read.
- **The gateway speaks two protocols.** Upstream to `server/llm` it is an
  OpenAI client; downstream to the browser it is an AI SDK **UI Message
  Stream** over SSE. Those are unrelated wire formats that both call themselves
  streaming, and the seam between them is where the first outage came from —
  the gateway emitted the AI SDK's retired `0:"text"` framing, which `ai@7`
  reads as an empty response and renders as nothing at all.
- **`nuxt-csurf` no longer guards chat.** It protects Nitro routes, and chat is
  not a Nitro route any more. The gateway's own bearer check is the control.
- **Two `.env` conventions in one repo.** Both Python services read `LLM_`
  prefixed variables, so the gateway's Supabase URL is `LLM_SUPABASE_URL` and
  its engine URL is the doubled-up `LLM_LLM_ENGINE_URL`.
- [0002](0002-host-the-frontend-on-vercel.md) still holds for the SPA, but it
  now describes half a deployment: the gateway needs a host with a persistent
  process, and it is the piece holding the service-role key.
- Anonymous chat is gone. The template scoped chats to `session.user?.id ||
  session.id`; a Supabase JWT has no anonymous form, so sign-in is required.
