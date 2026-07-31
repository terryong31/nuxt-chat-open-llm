## Description & Rationale

<!-- Explain the motivation behind this change. Matching our philosophy of "judgment over feature count", focus on *why* this change is necessary and how it improves the codebase. -->

## Type of Change

- [ ] Bug fix (non-breaking change fixing an issue)
- [ ] New feature (non-breaking change adding functionality)
- [ ] Refactor / Optimization (no behavior change)
- [ ] Architectural change / ADR (requires new record in `docs/adr/`)
- [ ] Documentation update

## Component Affected

- [ ] `apps/server/` (Python / MLX Inference Server)
- [ ] `apps/web/` (Nuxt 4 Chat UI)
- [ ] `packages/` (Shared Python packages)
- [ ] `docs/adr/` (Architecture Decision Records)
- [ ] Repository / CI / Tooling

## Related Issues / ADRs

<!-- Link related issues or ADR files using GitHub syntax (e.g. Closes #12, References ADR-0001) -->

## Verification & Testing Steps

<!-- Describe how you verified your changes. Include specific commands run or tests added. -->

- [ ] Ran `make check` locally (all linter and typecheck tests passed).
- [ ] Tested against running server / app instance.

## Checklist

- [ ] Code follows project invariants and matches surrounding style.
- [ ] Comments explain *why*, not *what*.
- [ ] Dependencies updated via `uv add` (Python) or `bun add` (Web) if modified (no hand-edited `pyproject.toml` or lockfiles).
- [ ] If changing architecture, a new record was added to `docs/adr/`.
