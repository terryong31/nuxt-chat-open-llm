# Contributing to Local LLM & Web Search Agent

Thank you for your interest in contributing to Local LLM.

This document outlines the guidelines and workflow for contributing to the repository.

---

## Development Stack & Tooling

To ensure consistency and speed across development environments, please use the following tooling:

- Python Package Manager: Use [uv](https://github.com/astral-sh/uv).
- Node / Frontend Package Manager: Use [bun](https://bun.sh) (do not use npm or yarn).
- Backend Framework: Python 3.14+ / FastAPI / MLX / LangGraph (in `src/`).
- Frontend Framework: Nuxt 4 / Nuxt UI / Tailwind CSS v4 / Vue 3 Composition API (in `chat-app/`).

---

## Setting Up Local Development

### With Mise (Recommended)

```bash
# 1. Prepare environment files
cp src/.env.example src/.env
cp chat-app/.env.example chat-app/.env

# 2. Run both backend & frontend concurrently
mise run dev:all

# Or run separately:
mise run dev:be    # Backend only
mise run dev:web   # Frontend only
```

### Manual Setup

#### 1. Backend (`src/`)

```bash
cd src
uv sync
cp .env.example .env
uv run main.py
```

#### 2. Frontend (`chat-app/`)

```bash
cd chat-app
bun install
cp .env.example .env
bun dev
```

---

## Code Standards & Guidelines

### Python Backend (`src/local_llm/`)
- Type Hints: Use strict Python type hinting across all functions and models (`from typing import ...`).
- Memory Management: When introducing new MLX models, ensure memory cleanup (`gc.collect()` and `mx.clear_cache()`) is implemented in `ModelManager`.
- Tool Definitions: All LLM tools must provide standard JSON schemas in `src/local_llm/tools/` and be registered in `registry.py`.
- Streaming Invariants: All streaming outputs MUST use Server-Sent Events format (`data: {...}\n\n`) and maintain strict isolation between `thinking`, `tool_call`, `tool_result`, `answer`, and `metrics` event types.

### Frontend (`chat-app/`)
- Composition API: Use `<script setup lang="ts">` for all Vue components.
- Linting & Typechecking: Ensure zero lint or TypeScript errors before submitting changes:
  ```bash
  cd chat-app
  bun run lint
  bun run typecheck
  ```
- Styling: Use Nuxt UI components and Tailwind CSS v4 utility classes.

---

## Git & Pull Request Workflow

1. Fork and Branch:
   ```bash
   git checkout -b feature/your-feature-name
   ```
2. Commit Conventions:
   Follow Conventional Commits:
   - `feat: add mistral model support`
   - `fix: prevent tool tags leaking into answer stream`
   - `perf: optimize unified memory prompt prefill`
   - `docs: update setup instructions in README`
3. Verify Locally:
   - Verify that `cd src && uv run python -c "from local_llm.main import app; print('Backend OK')"` passes.
   - Run `cd chat-app && bun run lint && bun run typecheck`.
4. Submit a Pull Request:
   - Provide a clear summary of changes, rationale, and testing steps.
   - Link any related issues or discussions.

---

## Questions & Support

If you have questions or encounter bugs, please open an issue on the [GitHub Issues](https://github.com/terryong31/local-llm/issues) page.
