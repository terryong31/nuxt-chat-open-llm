1. ~~Split into 3 modes, dev, stg and prod~~ done
2. ~~Langgraph integration~~ done — `server/api/app/agent/`
3. ~~Integrate supabase~~ done — see [ADR 0006](docs/adr/0006-move-the-bff-into-a-python-gateway.md)
4. Include test suites: unit, integration, lint, ruff and etc
   - `testpaths` already point at `server/{api,llm}/tests`; neither exists, so
     `pytest` collects nothing and exits zero. CI is green on no tests.
   - Start with `agent/stream.py` — a pure generator, no model or DB needed.
5. Include security (Cloudflare captcha, slowapi)
   - `APP_ENV=development` currently skips auth entirely and disables
     per-user filtering in `ChatService`.
6. Maybe use a secrets manager, still deciding
7. ~~Replace the placeholder model registry~~ done — the picker now reads
   `GET /v1/models` from the gateway, which proxies the engine.
8. ~~Raise the reply token budget~~ done — the gateway sends `LLM_MAX_TOKENS`
   (1024) and the engine accepts `max_completion_tokens` as well as
   `max_tokens`.
