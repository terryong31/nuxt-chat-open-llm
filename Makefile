# One entrypoint for a repo with two package managers. Every target delegates;
# no logic lives here. `make` alone lists what there is.
.DEFAULT_GOAL := help
.PHONY: help setup hooks dev repl web lint typecheck check clean

WEB := apps/web

help:  ## Show this help
	@grep -hE '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

setup: hooks  ## Install both halves and the git hooks
	cd $(WEB) && bun install

hooks:  ## Install git hooks (lefthook ships in the uv dev group)
	uv sync
	uv run lefthook install

dev:  ## Run the inference server on :8000
	uv run llm-server

repl:  ## Streaming REPL against a running server
	uv run llm-repl

web:  ## Run the Nuxt frontend on :3000
	cd $(WEB) && bun run dev

lint:  ## Lint and format-check both halves
	uv run ruff format --check apps/server
	uv run ruff check apps/server
	cd $(WEB) && bun run lint

typecheck:  ## Typecheck the frontend
	cd $(WEB) && bun run typecheck

check: lint typecheck  ## Everything CI runs

clean:  ## Drop generated environments and caches
	rm -rf .venv $(WEB)/node_modules $(WEB)/.nuxt $(WEB)/.output
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
