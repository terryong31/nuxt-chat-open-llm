# 0002 — Host the frontend on Vercel

Accepted · 2026-08-01

## Context

`@nuxthub/core` reads as Cloudflare lock-in. At 0.10.8 it isn't:

- db drivers `d1 | libsql | postgres | planetscale`; blob drivers
  `vercel-blob | cloudflare-r2 | s3 | fs`; `hosting: "vercel"` is a known value.
- Its one declared peer dependency is `@vercel/blob`.
- The generated config resolves to `libsql` (Turso) and `@vercel/blob` — not
  D1, not R2.
- `.env.example` holds four keys, all on the Vercel path: Turso URL and token,
  `BLOB_READ_WRITE_TOKEN`, `AI_GATEWAY_API_KEY`. No Cloudflare variable.

13 route handlers `import { db } from 'hub:db'`. The driver moves; they don't.

## Decision

Deploy to Vercel via Nitro's `vercel` preset. No code changes — set the
environment variables.

## Rejected

| Option | Why not |
| --- | --- |
| Cloudflare Workers via NuxtHub | Means swapping db to D1 and blob to R2 for no gain, and giving up zero-config AI Gateway |
| Node container | Reimplements storage the driver layer already provides |

## Consequences

- **`maxDuration` must be set on the chat function.** Hobby caps wall-clock at
  60 s; a long completion from a 7B model gets close. Nitro's Vercel preset
  types it, so this is config, not a workaround.
- AI Gateway stays zero-config, so hosted models sit beside the local one in
  the same picker — which is the SSM-vs-transformer comparison this project
  exists to make, available for free.
- The backend is not co-located. It lives on a Mac behind a tunnel
  ([0001](0001-run-the-server-natively.md)), so the frontend must handle the
  origin being offline as a normal state, not an error.
