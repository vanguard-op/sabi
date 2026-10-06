# Sabi platform commands. This Makefile is the single source of truth for build,
# test, and deploy commands: it runs identically on a developer machine and in CI
# (.github/workflows/ci.yml). Run `make` or `make help` for the target list.
#
# First run: `make setup` then `make up`.

SHELL := /bin/bash
.DEFAULT_GOAL := help

ENV ?= dev
TF_DIR := infra/terraform
GCP_TF_DIR := infra/terraform-gcp
GCP_FOUNDATION_DIR := infra/terraform-gcp/foundation
GCP_ENV ?= staging

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
        test test-backend test-ai test-mobile test-integration test-model-quality \
        catalog-generate catalog-check \
        lint lint-backend lint-ai lint-mobile format format-backend format-ai check \
        tf-init tf-fmt tf-validate tf-plan tf-apply tf-destroy \
        gcp-init gcp-fmt gcp-validate gcp-plan gcp-apply gcp-up gcp-stop gcp-destroy \
        gcp-foundation-init gcp-foundation-plan gcp-foundation-apply

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

# --- Sabi A2UI catalog (one authored copy) ---
# The catalog is authored once in apps/mobile/lib/a2ui/sabi_catalog_document.dart
# and generated into services/ai/core/catalogs/sabi_a2ui_v1.json, which the AI
# service ships (FEAT-011). `catalog-check` fails when the committed JSON and the
# authored Dart document disagree; run `catalog-generate` to rewrite the JSON.
# No database, secret, or provider is needed: this is a plain Dart script.
catalog-generate: ## Regenerate the AI catalog JSON from the authored Dart document
	@if [ -d apps/mobile ]; then cd apps/mobile && dart run lib/a2ui/generate_catalog.dart --write; else echo "skip: apps/mobile not present"; fi

catalog-check: ## Fail if the AI catalog JSON has drifted from the authored Dart document
	@if [ -d apps/mobile ]; then cd apps/mobile && dart run lib/a2ui/generate_catalog.dart --check; else echo "skip: apps/mobile not present"; fi

# --- Integration suite (cross-service, tests/**) ---
# The API and AI services each expose a top-level `app` package, so they cannot
# share one interpreter: each directory is run from its own service root, as
# tests/README.md documents. Neither run needs Postgres, Redis, or a provider.

# The model-quality attestation records the MQ-001/002/003 golden-set harness that
# model-quality.md requires but that this delivery does not ship. It fails on
# purpose to report the gap, and that gap is an accepted decision recorded at the
# phase gate, so this one test is kept out of the blocking gate and reported by
# `make test-model-quality`; everything else in tests/** gates. To run it inside
# the gate too, drop INTEGRATION_DESELECT from the command line.
INTEGRATION_DESELECT := --deselect tests/ai/test_model_quality_attestation.py::test_golden_set_and_evaluation_harness_are_absent_from_this_delivery

test-integration: ## Run the cross-service integration suite (tests/**)
	@if [ -d services/api ]; then export $(call venv_activate,services/api); cd services/api && python -m pytest ../../tests/api; else echo "skip: services/api not present"; fi
	@if [ -d services/ai ]; then export $(call venv_activate,services/ai); cd services/ai && python -m pytest ../../tests/ai $(INTEGRATION_DESELECT); else echo "skip: services/ai not present"; fi

test-model-quality: ## Report the model-quality attestation (non-blocking; records the MQ harness gap)
	@if [ -d services/ai ]; then export $(call venv_activate,services/ai); cd services/ai && python -m pytest ../../tests/ai/test_model_quality_attestation.py; else echo "skip: services/ai not present"; fi

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

check: lint test test-integration catalog-check ## What CI runs: lint, per-service unit suites, integration gate, catalog drift guard

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

# --- GCP staging (infra/terraform-gcp) ---
# The hosted staging environment of D-032/D-033. The three lifecycle workflows
# are manual by design and are wrapped here so the same commands run locally and
# in CI. Never run a paid gcp-apply without the operator's explicit go-ahead.
# Real values live outside the repo; copy the *.example files next to them.

gcp-init: ## Initialise the GCP Terraform stack for GCP_ENV (default staging)
	terraform -chdir=$(GCP_TF_DIR) init -backend-config=envs/$(GCP_ENV)/backend.hcl

gcp-fmt: ## Check the GCP Terraform formatting
	terraform -chdir=$(GCP_TF_DIR) fmt -check -recursive

gcp-validate: ## Validate the GCP Terraform without a backend or credentials
	terraform -chdir=$(GCP_TF_DIR) init -backend=false -input=false
	terraform -chdir=$(GCP_TF_DIR) validate

gcp-plan: ## Plan the GCP stack for GCP_ENV (default staging)
	terraform -chdir=$(GCP_TF_DIR) plan -var-file=envs/$(GCP_ENV)/terraform.tfvars

gcp-apply: ## Apply the GCP stack (paid; requires explicit go-ahead)
	terraform -chdir=$(GCP_TF_DIR) apply -var-file=envs/$(GCP_ENV)/terraform.tfvars

# The long-lived network foundation (D-058): API enablement, VPC, run subnet,
# private-services range and peering, database firewall. It costs nothing and
# `gcp-destroy` never removes it. `gcp-up` applies it before the workload root.

gcp-foundation-init: ## Initialise the GCP network foundation stack for GCP_ENV (default staging)
	terraform -chdir=$(GCP_FOUNDATION_DIR) init -backend-config=envs/$(GCP_ENV)/backend.hcl

gcp-foundation-plan: ## Plan the GCP network foundation for GCP_ENV (default staging)
	terraform -chdir=$(GCP_FOUNDATION_DIR) plan -var-file=envs/$(GCP_ENV)/terraform.tfvars

gcp-foundation-apply: ## Apply the GCP network foundation (free; long-lived, D-058)
	terraform -chdir=$(GCP_FOUNDATION_DIR) apply -var-file=envs/$(GCP_ENV)/terraform.tfvars

gcp-up: ## Bring the GCP staging environment up (dispatches the gcp-up workflow)
	gh workflow run gcp-up.yml

gcp-stop: ## Scale Cloud Run to zero and stop Cloud SQL (dispatches gcp-stop.yml)
	gh workflow run gcp-stop.yml

gcp-destroy: ## Destroy the GCP staging stack, retaining the state bucket
	gh workflow run gcp-destroy.yml -f confirm=destroy
