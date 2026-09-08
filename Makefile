.PHONY: help install hooks lock export test cov itest lint format check migrate revision run relay consumer up down logs seed

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "};{printf "\033[36m%-12s\033[0m %s\n", $$1, $$2}'

install:   ## Create .venv, install deps, and set up git hooks
	uv sync
	uv run pre-commit install --install-hooks
	uv run pre-commit install --hook-type pre-push

hooks:     ## Run every pre-commit hook against all files
	uv run pre-commit run --all-files

lock:      ## Regenerate uv.lock from pyproject.toml
	uv lock

export:    ## Export a pip-compatible requirements.txt from the lock
	uv export --no-dev --no-hashes --format requirements-txt > requirements.txt

test:      ## Unit tests (SQLite, no services needed)
	uv run pytest -v

cov:       ## Unit tests with coverage report
	uv run pytest --cov=app --cov-report=term-missing

itest:     ## Integration tests (needs PostgreSQL via DATABASE_URL)
	uv run pytest -v -m integration

lint:      ## Lint + verify formatting (no writes)
	uv run ruff check app tests scripts
	uv run ruff format --check app tests scripts

format:    ## Autofix lint issues and reformat
	uv run ruff check --fix app tests scripts
	uv run ruff format app tests scripts

check:     ## Everything CI runs, locally
	$(MAKE) lint
	uv run python scripts/check_single_head.py
	$(MAKE) test

migrate:   ## Apply migrations
	uv run alembic upgrade head

revision:  ## Autogenerate a migration: make revision m="add x"
	uv run alembic revision --autogenerate -m "$(m)"

run:       ## Run the API with reload
	uv run uvicorn app.main:app --reload

relay:     ## Run the outbox relay
	uv run python -m app.relay

consumer:  ## Run the notifications consumer
	uv run python -m app.consumers

seed:      ## Populate the database with demo data
	uv run python -m scripts.seed

up:        ## Start the full stack (api, relay, consumer, db, rabbitmq)
	docker compose up --build

down:      ## Stop the stack and remove volumes
	docker compose down -v

logs:      ## Tail all container logs
	docker compose logs -f
