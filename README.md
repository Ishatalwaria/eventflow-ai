# EventFlow AI

EventFlow AI is an event-driven workflow and operational intelligence platform. The project now includes the M0 foundation and the M1 event-ingestion vertical slice. The API authenticates clients, validates `order.created` version 1 events, stores each event with its initial workflow, processing log, and outbox message in one PostgreSQL transaction, and exposes event and workflow status. Kafka publication and downstream processing remain later milestones.

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

## API client credentials

Create a client credential with:

```sh
python -m django client_credentials create --name "local-demo"
```

The command prints a bearer token once. Store it in a password manager or local environment variable; the database stores only a password hash. Rotate an active client with `python -m django client_credentials rotate --client-id <CLIENT_UUID>` and revoke it with `python -m django client_credentials revoke --client-id <CLIENT_UUID>`. Rotation invalidates the old secret; revocation immediately disables the credential. Do not paste tokens into logs or commit them.

## Event API

M1 currently accepts the `order.created` event type at schema version `1`. Its payload requires `order_id`, a three-letter uppercase `currency`, non-negative `total_minor_units`, and at least one item with `sku` and positive `quantity`. Timestamps must include a timezone offset. Requests are limited to 256 KiB and batches to 50 events.

Submit an event with `POST /api/v1/events` and `Authorization: Bearer <CLIENT_UUID>.<SECRET>`. A newly accepted event returns `201`; reusing the same client, source, and idempotency key returns `200` with the original event and workflow IDs and `duplicate: true`. The database uniqueness constraint is authoritative, including under concurrent requests.

`POST /api/v1/events/batch` accepts `{"events": [...]}`. A batch is all-or-nothing: validation or persistence failure rolls back the full batch. Successful batches return each event’s IDs and duplicate flag. No request publishes to Kafka; the transactional outbox stores the handoff record for a later milestone.

Use `GET /api/v1/events/{event_id}`, `GET /api/v1/workflows/{workflow_id}`, and `GET /api/v1/workflows?state=RECEIVED` to inspect records belonging to the authenticated client. Workflow listing is paginated at 50 items per page. API errors use an `error` object with a stable code and request ID. Responses also include the `X-Request-ID` header.

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

The default pytest configuration uses an isolated in-memory SQLite database, so tests do not modify the development PostgreSQL database or require permission to create a test database. The concurrent uniqueness-race test is skipped under SQLite. To run it with PostgreSQL, configure `EVENTFLOW_TEST_DATABASE_URL` for a dedicated local test role and use `pytest --ds=config.settings.postgres_integration`. Django creates a temporary database, so only that isolated test role may need `CREATEDB`; do not grant it to the application or production role. Never point this test URL at production.

## Configuration

`config.settings.local` is used by default for local development. Set `DJANGO_SETTINGS_MODULE=config.settings.production` for production and provide a unique `DJANGO_SECRET_KEY`, explicit `ALLOWED_HOSTS`, and a TLS-enabled PostgreSQL `DATABASE_URL` through the deployment secret manager. Production settings reject local database hosts, weak/missing secrets, wildcard hosts, non-PostgreSQL databases, and disabled TLS. Prefer `sslmode=verify-full` with the provider's CA certificate when supported; the default enforced minimum is `sslmode=require`. Percent-encode reserved characters in the URL username or password. Do not commit `.env` or production credentials.

### Production database permissions

Use separate PostgreSQL login roles for the application and schema migrations. The application role should have only `CONNECT`, schema `USAGE`, and the required table DML (`SELECT`, `INSERT`, `UPDATE`, `DELETE`) and sequence (`USAGE`, `SELECT`) permissions. It must not be a superuser, database owner, or have `CREATEDB`/`CREATEROLE`. Give schema ownership and `CREATE` rights to a separate migration role used only by a deployment migration job. Set default privileges for objects created by the migration role so the application role receives the required DML rights. Store both URLs as separate deployment secrets. The API container runs as a non-root user and does not run migrations at startup; run `python -m django migrate --noinput` as the migration role during deployment.

For a new production database, a PostgreSQL administrator can provision roles along these lines (enter passwords interactively with `\\password`; never place them in SQL files or shell history):

```sql
CREATE ROLE eventflow_migrator LOGIN;
CREATE ROLE eventflow_app LOGIN;
CREATE DATABASE eventflow OWNER eventflow_migrator;
\connect eventflow
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT CONNECT ON DATABASE eventflow TO eventflow_app;
GRANT USAGE ON SCHEMA public TO eventflow_app;
ALTER DEFAULT PRIVILEGES FOR ROLE eventflow_migrator IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO eventflow_app;
ALTER DEFAULT PRIVILEGES FOR ROLE eventflow_migrator IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO eventflow_app;
\password eventflow_migrator
\password eventflow_app
```

Connect the migration job with the `eventflow_migrator` URL and the running API with the `eventflow_app` URL. For an existing database, have the DBA review current object owners and grants before changing them; the new-role example is not a drop-in ownership migration. The supplied `eventflow-user` value must not be given `CREATEDB` just to run the concurrency test. Create a distinct local-only test role if that test needs database-creation permission.

Docker Compose is for local development only. Its PostgreSQL/API ports bind to localhost, and it requires local secrets rather than using built-in password defaults. The Compose PostgreSQL initialization user is still a local development convenience; do not reuse it, its password, or this Compose database role model in production.

The M1 schema lives in PostgreSQL; Django migrations are in each model-owning app. Django's built-in authentication and session migrations are also applied by the setup commands.
