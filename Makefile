# Master Monorepo Entrypoint
.DEFAULT_GOAL := help
.PHONY: help setup hooks api llm dev dev-stg dev-prod web web-stg web-prod build-dev build-stg build-prod lint typecheck check clean

WEB := apps/web

help:  ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

setup: hooks  ## Install dependencies across monorepo
	cd $(WEB) && bun install
	uv sync

hooks:  ## Install git hooks
	uv sync
	uv run lefthook install

api:  ## Run the Application API Gateway (BFF) on :8000
	APP_ENV=development uv run api-server

llm:  ## Run the LLM Inference Microservice on :9000
	APP_ENV=development uv run llm-engine

dev:  ## Run API Gateway in DEV mode
	APP_ENV=development uv run api-server

dev-stg:  ## Run API Gateway in STAGING mode
	APP_ENV=staging uv run api-server

dev-prod:  ## Run API Gateway in PRODUCTION mode
	APP_ENV=production uv run api-server

web:  ## Run the Nuxt frontend in DEV mode on :3000
	cd $(WEB) && bun run dev

web-stg:  ## Run the Nuxt frontend in STAGING mode
	cd $(WEB) && bun run dev:stg

web-prod:  ## Run the Nuxt frontend in PRODUCTION mode
	cd $(WEB) && bun run dev:prod

build-dev:  ## Build Nuxt frontend for DEV
	cd $(WEB) && bun run build:dev

build-stg:  ## Build Nuxt frontend for STAGING
	cd $(WEB) && bun run build:stg

build-prod:  ## Build Nuxt frontend for PRODUCTION
	cd $(WEB) && bun run build:prod

MODEL := mlx-community/Mamba-Codestral-7B-v0.1-4bit
ADAPTERS := packages/finetune/adapters

finetune-data:  ## Regenerate LoRA training data
	uv run finetune-data

# Hyperparameters live in lora.yaml, not here: CLI flags override the file, so
# a stray flag on this line would silently win over a value whose comment
# explains why it has to be what it is.
finetune:  ## LoRA fine-tune for tool calling — STOP `make llm` first, it needs the RAM
	uv run python -m mlx_lm lora --train -c packages/finetune/lora.yaml

finetune-serve:  ## Run the engine with the trained adapter on :9000
	APP_ENV=development LLM_ADAPTER_PATH=$(ADAPTERS) uv run llm-engine

# Held-out prompts, so this measures generalisation rather than memorisation.
# Run both halves to get a before/after; each loads the checkpoint, so not
# while the engine is up.
finetune-eval-base:  ## Score tool-call compliance on the BASE checkpoint
	uv run finetune-eval --json packages/finetune/eval-base.json

finetune-eval:  ## Score tool-call compliance WITH the trained adapter
	uv run finetune-eval --adapter $(ADAPTERS) --json packages/finetune/eval-lora.json

lint:  ## Lint Python and JavaScript packages
	uv run ruff format --check server/api server/llm
	uv run ruff check server/api server/llm
	cd $(WEB) && bun run lint

typecheck:  ## Typecheck the frontend
	cd $(WEB) && bun run typecheck

check: lint typecheck  ## Run CI checks

clean:  ## Drop generated environments and caches
	rm -rf .venv $(WEB)/node_modules $(WEB)/.nuxt $(WEB)/.output
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
