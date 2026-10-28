# EventFlow AI

EventFlow AI is an event-driven workflow and operational intelligence platform. M0 provides the Django foundation, M1 accepts authenticated events transactionally, and M2 adds an at-least-once PostgreSQL outbox → Kafka → RabbitMQ → worker pipeline. PostgreSQL remains the transactional source of truth. See [the M2 topology and delivery notes](docs/m2-broker-topology.md).

## Requirements

- Python 3.12 (the Docker image uses the current patched Python 3.12 slim image)
- Docker Engine and Docker Compose v2 for the containerized setup

## Local setup

1. Create and activate a Python 3.12 virtual environment.
2. If `.env` does not exist, copy `.env.example` to `.env`; otherwise merge any missing variables without overwriting your existing values. Set unique local values for `DJANGO_SECRET_KEY`, `POSTGRES_PASSWORD`, and `RABBITMQ_PASSWORD`. Keep the database password in `DATABASE_URL` in sync with `POSTGRES_PASSWORD`; percent-encode reserved characters in the URL password.
3. Install the application and development tools:

   ```sh
   python -m pip install -e ".[dev]"
   ```

4. Start PostgreSQL, Kafka, RabbitMQ, the API, and workers. Compose applies migrations before starting the API and worker processes:

   ```sh
   docker compose up -d --build
   ```

The API is available at `http://localhost:8000`. Interactive OpenAPI documentation is at `/api/docs/`; the raw schema is at `/api/schema/`. For a host-run development server instead of the Compose API, stop the Compose API service first, then use `python manage.py runserver`.

## API client credentials

Create a client credential with:

```sh
python manage.py client_credentials create --name "local-demo"
```

The command prints a bearer token once. Store it in a password manager or local environment variable; the database stores only a password hash. Rotate an active client with `python manage.py client_credentials rotate --client-id <CLIENT_UUID>` and revoke it with `python manage.py client_credentials revoke --client-id <CLIENT_UUID>`. Rotation invalidates the old secret; revocation immediately disables the credential. Do not paste tokens into logs or commit them.

## Event API

M1 currently accepts the `order.created` event type at schema version `1`. Its payload requires `order_id`, a three-letter uppercase `currency`, non-negative `total_minor_units`, and at least one item with `sku` and positive `quantity`. Timestamps must include a timezone offset. Requests are limited to 256 KiB and batches to 50 events.

Submit an event with `POST /api/v1/events` and `Authorization: Bearer <CLIENT_UUID>.<SECRET>`. A newly accepted event returns `201`; reusing the same client, source, and idempotency key returns `200` with the original event and workflow IDs and `duplicate: true`. The database uniqueness constraint is authoritative, including under concurrent requests.

`POST /api/v1/events/batch` accepts `{"events": [...]}`. A batch is all-or-nothing: validation or persistence failure rolls back the full batch. Successful batches return each event’s IDs and duplicate flag. The request writes the Kafka handoff into the PostgreSQL outbox in the same transaction. A separate publisher sends it to Kafka after commit.

Use `GET /api/v1/events/{event_id}`, `GET /api/v1/workflows/{workflow_id}`, and `GET /api/v1/workflows?state=RECEIVED` to inspect records belonging to the authenticated client. Workflow listing is paginated at 50 items per page. API errors use an `error` object with a stable code and request ID. Responses also include the `X-Request-ID` header.

## Docker Compose

If `.env` does not exist, copy `.env.example` to `.env`; otherwise merge the documented variables without replacing your existing values. Set a strong local `RABBITMQ_PASSWORD` before the first broker start, then run:

```sh
docker compose up --build
```

Compose starts PostgreSQL, a single-node KRaft Kafka broker, RabbitMQ, the API, an outbox publisher, a Kafka-to-Rabbit consumer, and a workflow worker. Set `RABBITMQ_PASSWORD` in `.env` before running Compose. Ports bind to localhost. To stop the stack, run `docker compose down`; this preserves database and broker volumes. Do not use `-v` unless you intentionally want to delete local data.

RabbitMQ reads `RABBITMQ_DEFAULT_PASS` only when its data volume is initialized. If you change `RABBITMQ_PASSWORD` later, update the existing RabbitMQ user's password as well; changing `.env` alone does not rotate a credential already stored in the volume. The live RabbitMQ integration test uses the same `RABBITMQ_HOST`, `RABBITMQ_USERNAME`, `RABBITMQ_PASSWORD`, TLS, and CA settings as the application, and fails with a configuration message if those credentials do not match the running broker.

Inspect services and brokers:

```sh
docker compose ps
docker compose exec kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server kafka:9092 --list
docker compose exec rabbitmq rabbitmqctl list_queues name messages consumers
python manage.py outbox_status --check
```

RabbitMQ's management UI is available at `http://localhost:15672` using the local `.env` credentials. Kafka topics are explicitly created by `kafka-init`; the domain and lifecycle topics use three partitions. The local RabbitMQ topology uses quorum queues with a single replica and is for development only.

## Health endpoints

- `GET /health/live` returns `200 {"status":"ok"}` when the process can serve requests. It does not query PostgreSQL.
- `GET /health/ready` runs a short-timeout PostgreSQL query and returns `200 {"status":"ready","checks":{"database":"ok"}}` when available, or `503 {"status":"not_ready","checks":{"database":"unavailable"}}` otherwise.

## Developer checks

```sh
pytest
ruff check .
ruff format --check .
python manage.py check
```

The default pytest configuration uses an isolated in-memory SQLite database, so tests do not modify the development PostgreSQL database or require permission to create a test database. The concurrent uniqueness-race test is skipped under SQLite. To run it with PostgreSQL, configure `EVENTFLOW_TEST_DATABASE_URL` for a dedicated local test role and use `pytest --ds=config.settings.postgres_integration`. Django creates a temporary database, so only that isolated test role may need `CREATEDB`; do not grant it to the application or production role. Never point this test URL at production.

The default suite also contains unit tests for processing outcomes, retry limits, idempotency, crash-after-commit redelivery, and broker failures. Live Kafka/RabbitMQ adapter tests are marked `integration` and skipped unless explicitly enabled. With the local Compose brokers running, run these commands in PowerShell to publish and consume real broker messages:

```powershell
$env:EVENTFLOW_RUN_BROKER_INTEGRATION = "1"
pytest -m integration
```

The integration tests do not claim that every multi-container failure mode was exercised. DB/outbox failure behaviors are covered by unit tests; use the manual checks below for the full path.

To simulate a transient failure followed by success from PowerShell, create a client token and store it in `$env:EVENTFLOW_API_TOKEN`, then submit an event. The workflow first enters `RETRY_WAIT`, waits on the bounded retry queue, and should reach `SUCCEEDED` after about five seconds:

```powershell
curl.exe -X POST http://localhost:8000/api/v1/events `
  -H "Authorization: Bearer $env:EVENTFLOW_API_TOKEN" `
  -H "Content-Type: application/json" `
  -d '{"event_type":"order.created","schema_version":1,"source":"manual-check","idempotency_key":"retry-demo-001","occurred_at":"2026-10-27T00:00:00Z","correlation_id":"retry-demo-001","payload":{"order_id":"retry-demo-001","currency":"INR","total_minor_units":100,"items":[{"sku":"TEMPORARY-FAIL-FIRST","quantity":1}]}}'
```

For a permanent business failure, repeat with a new idempotency key and order ID, and change the item SKU to `OOS-MANUAL-CHECK`; the workflow should reach `FAILED` and appear in the dead-letter queue. Use the returned `workflow_id` with `curl.exe -H "Authorization: Bearer $env:EVENTFLOW_API_TOKEN" http://localhost:8000/api/v1/workflows/<WORKFLOW_UUID>`. Inspect dead letters with `docker compose exec rabbitmq rabbitmqctl list_queues name messages` and inspect the outbox with `python manage.py outbox_status`.

## Configuration

`manage.py` selects `config.settings.local` by default and loads values from `.env`. Set `DJANGO_SETTINGS_MODULE=config.settings.production` for production; the same entry point honors the deployment environment. Provide a unique `DJANGO_SECRET_KEY`, explicit `ALLOWED_HOSTS`, and TLS-enabled PostgreSQL, Kafka, and RabbitMQ endpoints through the deployment secret manager. Production settings reject local database/broker hosts, weak/missing secrets, wildcard hosts, non-PostgreSQL databases, plaintext Kafka, and plaintext RabbitMQ. Configure Kafka with `KAFKA_SECURITY_PROTOCOL=SSL` or `SASL_SSL`; SASL additionally requires its mechanism and credentials. Set `RABBITMQ_USE_TLS=true` and a dedicated user with a strong password. Prefer `sslmode=verify-full` for PostgreSQL and provide CA paths where required. Percent-encode reserved characters in the database URL username or password. Do not commit `.env` or production credentials.

### Production database permissions

Use separate PostgreSQL login roles for the application and schema migrations. The application role should have only `CONNECT`, schema `USAGE`, and the required table DML (`SELECT`, `INSERT`, `UPDATE`, `DELETE`) and sequence (`USAGE`, `SELECT`) permissions. It must not be a superuser, database owner, or have `CREATEDB`/`CREATEROLE`. Give schema ownership and `CREATE` rights to a separate migration role used only by a deployment migration job. Set default privileges for objects created by the migration role so the application role receives the required DML rights. Store both URLs as separate deployment secrets. The API container runs as a non-root user and does not run migrations at startup; run `python manage.py migrate --noinput` as the migration role during deployment.

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

The M2 schema extension lives in PostgreSQL; migrations include a data backfill for previously pending M1 outbox rows so their topic and envelope match the versioned Kafka contract. Django's built-in authentication and session migrations are also applied by the setup commands.
