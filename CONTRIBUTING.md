# Contributing to Local LLM & Web Search Agent

Thank you for your interest in contributing to Local LLM.

This document outlines the guidelines and workflow for contributing to the repository.

---

## Development Stack & Tooling

To ensure consistency and speed across development environments, please use the following tooling:

- Python Package Manager: Use [uv](https://github.com/astral-sh/uv).
- Node / Frontend Package Manager: Use [bun](https://bun.sh) (do not use npm or yarn).
- Backend Framework: Python 3.14+ / FastAPI / MLX / LangGraph.
- Frontend Framework: Nuxt 4 / Nuxt UI / Tailwind CSS v4 / Vue 3 Composition API.

---

## Setting Up Local Development

### 1. Backend

```bash
# Sync Python virtual environment
uv sync

# Ensure environment file exists
cp .env.example .env

# Run the FastAPI server
uv run main.py
```

### 2. Frontend

```bash
cd chat-app

# Install dependencies
bun install

# Run the development server
bun dev
```

---

## Code Standards & Guidelines

### Python Backend
- Type Hints: Use strict Python type hinting across all functions and models (`from typing import ...`).
- Memory Management: When introducing new MLX models, ensure memory cleanup (`gc.collect()` and `mx.clear_cache()`) is implemented in `ModelManager`.
- Tool Definitions: All LLM tools must provide standard JSON schemas in `tools/` and be wired into the ReAct loop in `agent/graph.py`.
- Streaming Invariants: All streaming outputs MUST use Server-Sent Events format (`data: {...}\n\n`) and maintain strict isolation between `thinking`, `tool_call`, `tool_result`, `answer`, and `metrics` event types.

### Frontend (Nuxt 4 / Vue 3)
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
   - Verify that `uv run main.py` starts cleanly and passes test queries.
   - Run `bun run lint && bun run typecheck` in `chat-app`.
4. Submit a Pull Request:
   - Provide a clear summary of changes, rationale, and testing steps.
   - Link any related issues or discussions.

---

## Questions & Support

If you have questions or encounter bugs, please open an issue on the [GitHub Issues](https://github.com/terryong31/local-llm/issues) page.
