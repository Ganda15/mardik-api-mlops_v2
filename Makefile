.PHONY: up down test serve fmt lint typecheck install

install:
	uv sync

up:
	docker compose up -d

down:
	docker compose down

serve:
	uv run uvicorn mardik_api.app:app --reload --port 8000

test:
	uv run pytest -v

fmt:
	uv run ruff format .
	uv run ruff check --fix .

lint:
	uv run ruff check .

typecheck:
	uv run mypy src
