# Sabi platform commands. This Makefile is the single source of truth for build,
# test, and deploy commands: it runs identically on a developer machine and in CI
# (.github/workflows/ci.yml). Run `make` or `make help` for the target list.
#
# First run: `make setup` then `make up`.

SHELL := /bin/bash
.DEFAULT_GOAL := help

ENV ?= dev
TF_DIR := infra/terraform

# Resolve a Python tool from a service's virtualenv when one is present, and from
# PATH otherwise (which is how CI runs after `pip install`). This keeps local and
# CI runs identical: local uses services/<svc>/.venv/bin/<tool>, CI uses the tool
# pip installed into the runner. Call it at the top of a recipe:
#   export $(call venv_activate,services/api); cd services/api && pytest
# It expands to a PATH assignment that prepends the venv's bin only when the venv
# exists; with no venv it is empty and pytest/ruff resolve from PATH as in CI.
venv_activate = $(if $(wildcard $(1)/.venv/bin/python),PATH="$(CURDIR)/$(1)/.venv/bin:$${PATH}",)

.PHONY: help setup up down reset logs ps migrate \
        backend-dev backend-serve ai-dev ai-serve mobile-dev mobile-build \
        test test-backend test-ai test-mobile \
        lint lint-backend lint-ai lint-mobile format format-backend format-ai check \
        tf-init tf-fmt tf-validate tf-plan tf-apply tf-destroy

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| sort \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

setup: ## Create .env from the template if missing
	@if [ -f .env ]; then echo ".env already exists"; else cp .env.example .env; echo "created .env"; fi

# --- Local dependencies ---

up: ## Start dev dependencies (Postgres + pgvector, Redis) and wait for healthy
	docker compose up -d --wait

down: ## Stop dev dependencies, keeping data
	docker compose down

reset: ## Stop dev dependencies and delete volumes
	docker compose down -v

logs: ## Follow dev dependency logs
	docker compose logs -f

ps: ## Show dev dependency status
	docker compose ps

# --- Application processes (run on the host) ---

backend-dev: ## Run the API with reload (http://localhost:8000)
	cd services/api && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

backend-serve: ## Boot the API without reload (production command)
	cd services/api && uvicorn app.main:app --host $${API_HOST:-0.0.0.0} --port $${API_PORT:-8000}

ai-dev: ## Run the AI service with reload (http://localhost:8001)
	cd services/ai && uvicorn app.main:app --reload --host 0.0.0.0 --port 8001

ai-serve: ## Boot the AI service without reload (production command)
	cd services/ai && uvicorn app.main:app --host $${AI_HOST:-0.0.0.0} --port $${AI_PORT:-8001}

mobile-dev: ## Run the Flutter client
	cd apps/mobile && flutter run

mobile-build: ## Bundle the Android release (add `--build-name` at release time)
	@if [ -d apps/mobile ]; then cd apps/mobile && flutter build appbundle --release; else echo "skip: apps/mobile not present"; fi

migrate: ## Apply database migrations
	@if [ -d services/api ]; then export $(call venv_activate,services/api); cd services/api && alembic upgrade head; else echo "skip: services/api not present"; fi

# --- Tests ---

test-backend: ## Run API tests
	@if [ -d services/api ]; then export $(call venv_activate,services/api); cd services/api && pytest; else echo "skip: services/api not present"; fi

test-ai: ## Run AI tests
	@if [ -d services/ai ]; then export $(call venv_activate,services/ai); cd services/ai && pytest; else echo "skip: services/ai not present"; fi

test-mobile: ## Run Flutter tests
	@if [ -d apps/mobile ]; then cd apps/mobile && flutter test; else echo "skip: apps/mobile not present"; fi

test: test-backend test-ai test-mobile ## Run every test suite

# --- Lint / format ---

lint-backend: ## Lint the API service
	@if [ -d services/api ]; then export $(call venv_activate,services/api); cd services/api && ruff check .; else echo "skip: services/api not present"; fi

lint-ai: ## Lint the AI service
	@if [ -d services/ai ]; then export $(call venv_activate,services/ai); cd services/ai && ruff check .; else echo "skip: services/ai not present"; fi

lint-mobile: ## Analyze the Flutter client
	@if [ -d apps/mobile ]; then cd apps/mobile && flutter analyze; else echo "skip: apps/mobile not present"; fi

lint: lint-backend lint-ai lint-mobile ## Lint every service

format-backend: ## Auto-format the API service
	@if [ -d services/api ]; then export $(call venv_activate,services/api); cd services/api && ruff format . && ruff check --fix .; else echo "skip: services/api not present"; fi

format-ai: ## Auto-format the AI service
	@if [ -d services/ai ]; then export $(call venv_activate,services/ai); cd services/ai && ruff format . && ruff check --fix .; else echo "skip: services/ai not present"; fi

format: format-backend format-ai ## Auto-format every Python service

check: lint test ## What CI runs: lint then the full test suite

# --- Deployment (infra/terraform) ---
# Real variable and backend values live outside the repo; copy the *.example
# files next to them. CI validates with `-backend=false` and no credentials.

tf-init: ## Initialise Terraform for ENV (default dev)
	terraform -chdir=$(TF_DIR) init -backend-config=envs/$(ENV)/backend.hcl

tf-fmt: ## Check Terraform formatting
	terraform -chdir=$(TF_DIR) fmt -check -recursive

tf-validate: ## Validate Terraform without a backend or credentials
	terraform -chdir=$(TF_DIR) init -backend=false -input=false
	terraform -chdir=$(TF_DIR) validate

tf-plan: ## Plan ENV (default dev)
	terraform -chdir=$(TF_DIR) plan -var-file=envs/$(ENV)/terraform.tfvars

tf-apply: ## Apply ENV (default dev)
	terraform -chdir=$(TF_DIR) apply -var-file=envs/$(ENV)/terraform.tfvars

tf-destroy: ## Destroy ENV (default dev)
	terraform -chdir=$(TF_DIR) destroy -var-file=envs/$(ENV)/terraform.tfvars
