.PHONY: install run test lint format check migrate compose-up compose-down

install:
	python -m pip install -e ".[dev]"

run:
	python -m django runserver 0.0.0.0:8000

test:
	pytest

lint:
	ruff check .
	ruff format --check .

format:
	ruff check --fix .
	ruff format .

check:
	python -m django check
	pytest
	ruff check .

migrate:
	python -m django migrate

compose-up:
	docker compose up --build

compose-down:
	docker compose down
