.PHONY: install run test lint format check migrate compose-up compose-down

install:
	uv sync --frozen --extra dev

run:
	python manage.py runserver 0.0.0.0:8000

test:
	uv run --frozen --extra dev pytest

lint:
	uv run --frozen --extra dev ruff check .
	uv run --frozen --extra dev ruff format --check .

format:
	ruff check --fix .
	ruff format .

check:
	uv run --frozen --extra dev python manage.py check
	uv run --frozen --extra dev pytest
	uv run --frozen --extra dev ruff check .

audit:
	uv run --frozen --extra dev pip-audit --strict

migrate:
	python manage.py migrate

compose-up:
	docker compose up --build

compose-down:
	docker compose down
