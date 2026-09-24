# Dora X Classify — one-command workflows (Docker only; no local Python/Node needed).
COMPOSE      = docker compose
COMPOSE_PROD = docker compose -f docker-compose.prod.yml

.DEFAULT_GOAL := help
.PHONY: help up dev down logs ps restart test test-backend test-frontend seed shell-backend shell-frontend \
        prod-up prod-down clean

help:  ## Show available commands
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

up: ## Start MongoDB + backend (hot reload) + frontend (HMR) — http://localhost:5173
	$(COMPOSE) up --build --renew-anon-volumes

dev: up ## Alias for `make up`

down: ## Stop the dev stack (keeps MongoDB data)
	$(COMPOSE) down

logs: ## Follow logs of all services
	$(COMPOSE) logs -f

ps: ## Show service status
	$(COMPOSE) ps

restart: ## Restart backend and frontend
	$(COMPOSE) restart backend frontend

test: test-backend test-frontend ## Run all backend and frontend tests in containers

test-backend: ## Run pytest in the backend dev image
	$(COMPOSE) --profile test run --rm --build backend-tests

test-frontend: ## Run vitest in the frontend dev image
	$(COMPOSE) --profile test run --rm --build frontend-tests

seed: ## Wipe and reseed demo data (stack must be running)
	$(COMPOSE) exec backend python -m app.seed --reset

shell-backend: ## Shell inside the backend container
	$(COMPOSE) exec backend bash

shell-frontend: ## Shell inside the frontend container
	$(COMPOSE) exec frontend sh

prod-up: ## Production-like images (nginx + non-root API) — http://localhost:8080
	$(COMPOSE_PROD) up --build -d

prod-down: ## Stop the production-like stack
	$(COMPOSE_PROD) down

clean: ## Stop everything and delete volumes (MongoDB data, recordings)
	$(COMPOSE) down -v --remove-orphans
	$(COMPOSE_PROD) down -v --remove-orphans
