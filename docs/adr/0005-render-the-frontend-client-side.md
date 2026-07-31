# 0005 — Render the frontend client-side

Accepted · 2026-08-01

## Context

The template shipped with SSR on. Nothing in this app benefits from it, and one
thing is actively broken by it: the UI reads wall clock time during render.
`app/pages/index.vue` picks a greeting from `new Date().getHours()`, and
`app/composables/useChats.ts` buckets the sidebar into Today / Yesterday with
`date-fns`. Rendered on a UTC function and rehydrated in the user's timezone,
both disagree with themselves — measured at UTC+8, the server says evening while
the browser says morning.

Nothing here is crawlable either: chat is per-session and dynamic.

A separate question got tangled with this one — whether `server/api/` could
move into composables, given the inference backend already lives on a Mac
([0001](0001-run-the-server-natively.md)). It cannot. Of 14 server files, 12
import `hub:db` and 13 read the session. That layer is the database, the OAuth
secret holder, the cookie seal, and the place the tunnel credential stays out
of the browser. Rendering mode and data ownership are independent choices;
only the first one is being made here.

## Decision

`ssr: false`, plus `nitro.prerender.routes: ['/']`. Nitro and every route under
`server/` are untouched.

## Rejected

| Option | Why not |
| --- | --- |
| Keep SSR, patch the clock reads | Two `ClientOnly` wrappers to buy a server render nobody reads |
| `ssr: false` alone | Leaves the shell rendered per request; the CDN never answers the document |
| Static export (`nuxt generate`) | Deletes the API routes the app is built on |
| Server routes → composables | Ships the database token, the tunnel token, and the GitHub secret to the browser |

## Consequences

- Public shared chats (`visibility: 'public'`) lose link previews and crawlable
  text. If that matters, add one prerendered OG route — don't restore SSR.
- Every fetch is now a client waterfall, so anything awaited at the top of a
  component blocks paint. The layout's chat list is lazy, and the conversation
  moved to `ChatConversation` behind a `<Suspense>` so the page itself stays
  synchronous.
- A blank shell needs a loader: `app/spa-loading-template.html` renders before
  the stylesheet arrives, so it carries its own inline CSS.
- Deep links still wake the renderer function. That render touches no database,
  and the majority path — `/` — is now a static file.
