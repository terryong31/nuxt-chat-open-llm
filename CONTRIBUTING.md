# Contributing to ssm-mistral-mamba-chatbot

Thank you for your interest in contributing to **ssm-mistral-mamba-chatbot**! This repository hosts a coding chatbot powered by a State Space Model (Mamba-Codestral 7B) running locally via MLX on Apple Silicon, paired with a modern Nuxt 4 web application.

---

## 1. Project Philosophy & Core Principles

This repository is a **portfolio project where judgment is prioritized over feature count**. We value quality, architectural clarity, and small, well-reasoned iterations.

- **Prefer small, focused changes**: Keep pull requests atomic and easy to review.
- **Explain why, not what**: Comments and documentation should detail the intent, constraints, and rationale behind code rather than restating the obvious.
- **Project Naming**: The repository directory is named `local-llm`, but the project identity is **`ssm-mistral-mamba-chatbot`**. Please use `ssm-mistral-mamba-chatbot` in prose, documentation, and package descriptions.
- **Architectural Decision Records**: Significant technical decisions are recorded as ADRs in `docs/adr/`. If a change alters established architecture, document the choice in a new ADR record rather than editing past ADR entries.

---

## 2. Directory & Component Map

The repository is structured as a monorepo containing a Python `uv` workspace and a Nuxt/Bun web project:

| Path | Description | Nested Guidance |
| :--- | :--- | :--- |
| `apps/server/` | MLX inference engine & FastAPI OpenAI-compatible server | [apps/server/CLAUDE.md](apps/server/CLAUDE.md) |
| `apps/web/` | Nuxt 4 Chat UI (Nuxt UI, Nitro, Drizzle ORM, Vercel AI SDK) | [apps/web/CLAUDE.md](apps/web/CLAUDE.md) |
| `packages/` | Shared Python members and future benchmarks | — |
| `docs/adr/` | Architectural Decision Records explaining system design choices | [docs/adr/README.md](docs/adr/README.md) |

---

## 3. Prerequisites & Environment Setup

### System Requirements
- **macOS with Apple Silicon (M1/M2/M3/M4)**: Required for MLX GPU acceleration via Metal.
- **Python**: `>= 3.14` managed via [`uv`](https://github.com/astral-sh/uv).
- **Node.js & Bun**: [`bun`](https://bun.sh) for managing and running the Nuxt web application.

### Setting Up the Environment

1. **Clone the repository**:
   ```bash
   git clone https://github.com/terryong31/ssm-mistral-mamba-chatbot.git
   cd ssm-mistral-mamba-chatbot
   ```

2. **Run setup**:
   Execute the Makefile setup task to install dependencies and configure Git hooks:
   ```bash
   make setup
   ```
   This executes:
   - `uv sync`: Creates a root virtual environment (`.venv`) and installs Python workspace members and development dependencies.
   - `cd apps/web && bun install`: Installs Node dependencies for the Nuxt frontend.
   - Wires Git hooks via `lefthook`.

3. **Configure Environment Variables**:
   Copy example environment files where needed:
   ```bash
   cp apps/server/.env.example apps/server/.env
   cp apps/web/.env.example apps/web/.env
   ```

---

## 4. Development Workflow & Commands

A top-level [Makefile](Makefile) standardizes commands across both package managers.

### Common Commands

```bash
make help       # List available Makefile targets
make dev        # Run the Python inference server on http://127.0.0.1:8000
make web        # Run the Nuxt frontend on http://localhost:3000
make repl       # Launch the streaming CLI REPL against a running server
make check      # Run all linters and typechecks (Python + Web)
make clean      # Remove virtual environments, node_modules, and build caches
```

### Python Package Management (`uv`)
Python dependencies are managed via a single `uv` workspace at the root. **Never edit `pyproject.toml` or `uv.lock` by hand.**

- Add a dependency to the server package:
  ```bash
  uv add --package llm-server <package-name>
  ```
- Run Python commands inside the workspace virtual environment:
  ```bash
  uv run llm-server
  uv run pytest
  ```

### Web Package Management (`bun`)
The web application manages its dependencies separately via `apps/web/package.json`.

- Add a dependency to the frontend:
  ```bash
  cd apps/web && bun add <package-name>
  ```
- Run database migrations:
  ```bash
  cd apps/web && bun run db:generate
  cd apps/web && bun run db:migrate
  ```

---

## 5. Code Quality & Automated Checks

### Linters and Formatters
- **Python**: Managed with [Ruff](https://github.com/astral-sh/ruff) (line length 88, py314 target).
  ```bash
  uv run ruff check apps/server
  uv run ruff format apps/server
  ```
- **Web**: Managed with ESLint and TypeScript compiler.
  ```bash
  cd apps/web && bun run lint
  cd apps/web && bun run typecheck
  ```

### Git Hooks (`lefthook`)
[lefthook.yml](lefthook.yml) runs automated checks during Git lifecycle events:

- **`pre-commit`**: Automatically runs `ruff format`, `ruff check --fix`, and `eslint --fix` on staged files.
- **`pre-push`**: Verifies `uv.lock` integrity (`uv lock --check`), runs server linting (`ruff`), executes tests (`pytest`), and runs web typechecking (`bun run typecheck`).

To run the full suite manually before pushing:
```bash
make check
```

---

## 6. Engineering Invariants & Coding Guidelines

### Server Invariants (`apps/server/`)
- **Single Generation Workload**: MLX operations are not thread-safe. Execution serialization is enforced by `ThreadPoolExecutor(max_workers=1)`.
- **Lifespan Weight Loading**: Model weights must be loaded during FastAPI app startup (lifespan context), never at module import time.
- **Single Process Execution**: Do not run the server with multiple workers (`workers > 1`) or auto-reload (`reload=True`), as this duplicates multi-gigabyte memory allocations.
- **Non-blocking SSE Generators**: Pull the first stream event inside the route handler prior to returning a `StreamingResponse` so admission or readiness errors yield standard HTTP error statuses.

### Web Invariants (`apps/web/`)
- **Nuxt Auto-Imports**: Utilize Nuxt's auto-import capabilities for composables, components, and `#shared` modules. Avoid unnecessary explicit import statements.
- **API Request Validation**: Validate incoming routes and pay attention to Zod schema definitions for requests passing to the LLM server.
- **Database Schema Changes**: Keep Drizzle ORM schemas in sync by generating and running migrations upon modifying `apps/web/server/db/schema.ts`.

---

## 7. Submitting Issues & Feature Proposals

We welcome bug reports and feature proposals submitted via GitHub Issues using our structured templates:

- **Bug Reports**: Submit via [.github/ISSUE_TEMPLATE/bug_report.yml](.github/ISSUE_TEMPLATE/bug_report.yml). Include system hardware context (Apple Silicon generation), Python/uv/Bun versions, model checkpoint name, and reproduction steps.
- **Feature Requests & Proposals**: Submit via [.github/ISSUE_TEMPLATE/feature_request.yml](.github/ISSUE_TEMPLATE/feature_request.yml). Make sure to state the problem rationale, proposed solution, and whether the change requires an Architecture Decision Record in `docs/adr/`.

---

## 8. Pull Requests & Labeling Conventions

### Submitting a Pull Request
1. **Use the PR Template**: Pull requests automatically populate with [.github/PULL_REQUEST_TEMPLATE.md](.github/PULL_REQUEST_TEMPLATE.md). Complete all sections including motivation ("why"), component classification, and testing steps.
2. **Branch Naming**: Use clear prefixes:
   - `feat/description`
   - `fix/description`
   - `docs/description`
   - `refactor/description`
3. **Commit Messages**: Write concise imperative commit messages (e.g. `Add SSE cancellation check to streaming handler`). Explain intent for non-obvious changes.
4. **PR Verification Checklist**:
   - [ ] All linters and typecheckers pass (`make check`).
   - [ ] Python dependencies were updated via `uv add` if modified (and `uv.lock` is committed).
   - [ ] Architectural changes include a new ADR in `docs/adr/`.

### Repository Label Scheme
Issues and Pull Requests are categorized according to [.github/labels.yml](.github/labels.yml):

| Label Category | Examples | Description |
| :--- | :--- | :--- |
| **Component Area** | `area: server`, `area: web`, `area: packages`, `area: docs`, `area: infra` | Identifies which workspace member or subsystem is affected |
| **Change Type** | `type: bug`, `type: feature`, `type: refactor`, `type: adr` | Classifies the intent of the issue or PR |
| **Status / Priority** | `status: help wanted`, `status: good first issue`, `status: needs adr`, `status: blocked` | Tracks review/triage state |

---

## 9. Testing Guidelines

### Server Testing
- Unit and integration tests reside in `apps/server/tests/`.
- Use `pytest` with `pytest-asyncio` for asynchronous tests.
- When testing HTTP routes or orchestration logic, substitute `FakeEngine` to bypass loading the full 3.8 GB model checkpoint:
  ```python
  app = create_app(settings=Settings(...), engine=FakeEngine())
  ```

---

## 10. Code of Conduct

We are committed to providing a welcoming, inclusive, and harassment-free environment for everyone. Contributors are expected to maintain professional, constructive, and respectful communication in code reviews, issue discussions, and pull requests.
