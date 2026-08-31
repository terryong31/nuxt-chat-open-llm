# AGENTS.md — Lean Architecture & Operational Spec for Local LLM

This document is the authoritative **Lean Specification** for AI agents (and engineers) modifying or extending the `local-llm` codebase.

---

## 1. System Architecture & Tech Stack

```mermaid
graph TD
    subgraph Frontend ["Frontend (chat-app)"]
        UI["Nuxt 4 + Nuxt UI (Tailwind CSS v4)"]
        Client["SSE Streaming Client & Live Telemetry Dashboard"]
        UI --- Client
    end

    subgraph Backend ["Backend (src/local_llm - FastAPI + Python 3.14)"]
        API["API Layer (src/local_llm/api)"]
        MM["ModelManager (src/local_llm/models)"]
        LG["LangGraph ReAct Engine (src/local_llm/agent)"]
        MLX["MLX-LM (Metal GPU Acceleration on Apple Silicon)"]
        
        API --> MM
        API --> LG
        LG --> MLX
    end

    subgraph Tools ["Tools Layer (src/local_llm/tools)"]
        DDGS["DuckDuckGo Search (ddgs)"]
        Traf["Web Page Fetcher (trafilatura)"]
    end

    Client -->|SSE Stream POST /chat| API
    LG -->|Tool Execution| Tools
    Tools -->|Context & Results| LG
```

---

## 2. Core Architectural Invariants (DO NOT BREAK)

### A. Model Memory Lifecycle (`src/local_llm/models/manager.py` & `src/local_llm/main.py`)
1. **Lean Startup**: On application startup (`ModelManager.preload_default_model()`), only the default model (`settings.DEFAULT_MODEL`) is loaded to keep memory usage under ~10GB.
2. **On-Demand Dynamic Swap**: When an API request targets a different model (`ModelManager.activate_model()`), the manager unloads the active model, runs `gc.collect()`, executes `mx.clear_cache()`, and loads the new model so total memory usage never exceeds the single-model footprint.
3. **Shutdown Memory Flush**: On `KeyboardInterrupt` / FastAPI lifespan shutdown, `ModelManager.unload_all()` MUST clear all model references, run `gc.collect()`, and execute `mx.clear_cache()`.

### B. Streaming Protocol & Event Schema
The backend streams Server-Sent Events (`data: <JSON>\n\n`) with the following strict event types:
- `{"type": "thinking", "token": "..."}`: Internal reasoning tokens inside `<think>...</think>`.
- `{"type": "tool_call", "tool_name": "...", "tool_call_id": "...", "args": {...}}`: Intercepted tool call.
- `{"type": "tool_result", "tool_name": "...", "tool_call_id": "...", "result": [...]}`: Result payload from tool execution.
- `{"type": "answer", "token": "..."}`: Final markdown response tokens.
- `{"type": "metrics", "metrics": {...}}`: Hardware & generation telemetry payload.
- `data: [DONE]`: Stream completion indicator.

### C. Strict Thinking & Tool Tag Isolation (`src/local_llm/agent/engine.py`)
- **Thinking Boundary**: Tokens generated before `</think>` MUST route **exclusively** to `thinking` events and NEVER leak to `answer`.
- **Tool Interception**: XML tags (`<tool_call>`, `<function=...>`, `<parameter=...>`) must be intercepted and swallowed in the post-thinking buffer.
- **Deterministic Synthesis**: After tool calls finish, the agent MUST trigger a synthesis pass with an explicit directive to force complete markdown generation without infinite search loops.

---

## 3. Directory Map & Responsibilities

| Path | Purpose |
| :--- | :--- |
| `src/main.py` | Backend launcher delegating to `local_llm.main:app`. |
| `src/local_llm/main.py` | FastAPI application factory, CORS setup, and lifespan lifecycle. |
| `src/local_llm/core/config.py` | Pydantic `BaseSettings` for env vars, CORS, and model defaults. |
| `src/local_llm/schemas/` | Pydantic DTOs (`ChatMessage`, `ChatRequest`, `ChatResponse`, `MetricsResponse`). |
| `src/local_llm/models/manager.py`| `ModelManager` Unified Memory preloader and instant activation cache. |
| `src/local_llm/agent/graph.py` | LangGraph ReAct StateGraph definition and nodes. |
| `src/local_llm/agent/engine.py`| Deterministic 2-phase streaming generator (`stream_graph_chat`). |
| `src/local_llm/agent/parser.py`| Tool call XML regex extraction and fallback parser. |
| `src/local_llm/tools/web_search.py` | DuckDuckGo search (`perform_web_search`) and Trafilatura fetcher (`perform_web_fetch`). |
| `src/local_llm/api/` | Versioned API routes (`/chat`, `/health`, `/`). |
| `chat-app/` | Nuxt 4 frontend application. |
| `chat-app/shared/utils/models.ts` | Available model metadata and dropdown definitions. |
| `chat-app/app/pages/chat/[id].vue`| Main chat interface and SSE streaming event handler. |

---

## 4. Development & Verification Rules

### Package Management Rules
- **Backend**: Always use `uv` in `src/` (e.g. `cd src && uv sync`, `uv run main.py`, `uv pip install ...`).
- **Frontend**: Always use `bun` in `chat-app/` (e.g. `cd chat-app && bun install`, `bun dev`, `bun run lint`). Never use `npm` or `yarn`.

### Adding a New Model
1. Add model Hugging Face ID to `SUPPORTED_MODELS` in `src/local_llm/core/config.py`.
2. Add model entry (label, value, icon) to `chat-app/shared/utils/models.ts`.
3. Verify memory footprint fits within Apple Silicon Unified Memory.

### Adding a New Tool
1. Define the tool schema in `src/local_llm/tools/` using OpenAI/Qwen compatible JSON schema.
2. Implement the Python execution function.
3. Wire the tool definition into `src/local_llm/tools/registry.py` and execution branch into `src/local_llm/agent/graph.py`.

### Verification Checklist Before Commits
```bash
# Using Mise (Root)
mise run check:be
mise run lint
mise run typecheck

# Or Manual Execution:
# 1. Backend Verification
cd src
uv run python -c "from local_llm.models.manager import ModelManager; print('Backend OK')"

# 2. Frontend Lint & Typecheck
cd chat-app
bun run lint
bun run typecheck
```
