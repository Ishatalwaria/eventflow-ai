# EventFlow AI

EventFlow AI is an event-driven workflow and operational intelligence platform. This repository currently contains the M0 Django foundation: API configuration, PostgreSQL-backed readiness, OpenAPI documentation, and local development setup. Event processing and broker integrations are later milestones.

## Requirements

- Python 3.14
- Docker Engine and Docker Compose v2 for the containerized setup

## Local setup

1. Create and activate a Python 3.14 virtual environment.
2. Copy `.env.example` to `.env`. Replace the `DJANGO_SECRET_KEY` and `POSTGRES_PASSWORD` placeholders. Keep the password in `DATABASE_URL` in sync with `POSTGRES_PASSWORD`; percent-encode reserved characters in the URL password.
3. Install the application and development tools:

   ```sh
   python -m pip install -e ".[dev]"
   ```

4. Start PostgreSQL and apply Django's built-in migrations:

   ```sh
   docker compose up -d db
   python -m django migrate
   ```

5. Start the API:

   ```sh
   python -m django runserver
   ```

The API is available at `http://localhost:8000`. Interactive OpenAPI documentation is at `/api/docs/`; the raw schema is at `/api/schema/`.

## Docker Compose

Copy `.env.example` to `.env`, then run:

```sh
docker compose up --build
```

Compose starts PostgreSQL and the API. The API container applies Django's built-in migrations before starting. To stop the stack, run `docker compose down`. Add `-v` only when you intentionally want to remove the local database volume.

## Health endpoints

- `GET /health/live` returns `200 {"status":"ok"}` when the process can serve requests. It does not query PostgreSQL.
- `GET /health/ready` runs a short-timeout PostgreSQL query and returns `200 {"status":"ready","checks":{"database":"ok"}}` when available, or `503 {"status":"not_ready","checks":{"database":"unavailable"}}` otherwise.

## Developer checks

```sh
pytest
ruff check .
ruff format --check .
python -m django check
```

The readiness tests mock database connectivity and do not require a running PostgreSQL service. To verify a real local connection, start Compose and request `/health/ready`.

## Configuration

`config.settings.local` is used by default for local development. Set `DJANGO_SETTINGS_MODULE=config.settings.production` for production and provide `DJANGO_SECRET_KEY` and `ALLOWED_HOSTS` through the environment. Set `DATABASE_URL` to a PostgreSQL URL to configure the database; it takes precedence over the individual `POSTGRES_*` settings. If `DATABASE_URL` is omitted, `POSTGRES_PASSWORD` is required. Percent-encode reserved characters in the URL username or password. Compose connects the API to its database service using the `POSTGRES_*` settings. The production settings reject a missing secret key and enable secure session and CSRF cookies. Do not commit `.env` or production credentials.

No EventFlow domain models exist in M0, so no app migrations are generated. Django's built-in authentication and session migrations are applied by the setup commands.
