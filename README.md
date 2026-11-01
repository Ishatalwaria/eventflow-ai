# EventFlow AI

EventFlow AI is an event-driven workflow and operational intelligence platform. M0 provides the Django foundation, M1 accepts authenticated events transactionally, and M2 adds an at-least-once PostgreSQL outbox → Kafka → RabbitMQ → worker pipeline. PostgreSQL remains the transactional source of truth. See [the M2 topology and delivery notes](docs/m2-broker-topology.md).

## Requirements

- Python 3.12 (the Docker image uses a patched Python 3.12 slim image)
- uv 0.13.6 for the locked local and container dependencies
- Docker Engine and Docker Compose v2 for the containerized setup

## Local setup

1. Create and activate a Python 3.12 virtual environment.
2. If `.env` does not exist, copy `.env.example` to `.env`; otherwise merge any missing variables without overwriting your existing values. Set unique local values for `DJANGO_SECRET_KEY`, `POSTGRES_PASSWORD`, and `RABBITMQ_PASSWORD`. Keep the database password in `DATABASE_URL` in sync with `POSTGRES_PASSWORD`; percent-encode reserved characters in the URL password.
3. Install the locked application and development tools:

   ```sh
   uv sync --frozen --extra dev
   ```

4. Start PostgreSQL, Kafka, RabbitMQ, the API, and workers. Compose applies migrations before starting the API and worker processes:

   ```sh
   docker compose up -d --build
   ```

The API is available at `http://localhost:8000`. Interactive OpenAPI documentation is at `/api/docs/`; the raw schema is at `/api/schema/`. For a host-run development server instead of the Compose API, stop the Compose API service first, then use `uv run --frozen --extra dev python manage.py runserver`.

## Frontend dashboard

The React dashboard lives in `frontend/`. From that directory, install the locked packages and start Vite:

```sh
npm ci
npm run dev
```

Set `VITE_API_BASE_URL=http://localhost:8000` in `frontend/.env` when the API uses the default local port. Vite proxies API and health requests during development. Add a client bearer token in Settings; the token exists in browser memory only and is intended for local/demo use. Production user sessions should be mediated by a server-side backend-for-frontend.

Overview data comes from the authenticated tenant summary API and is scoped to the connected API client. Analytics uses the tenant-scoped PostgreSQL current-state report by default. The separate ClickHouse lifecycle report remains system-wide and requires the explicit `can_view_analytics` capability. System Health performs bounded server-side checks and scrapes allowlisted worker metrics with the server-held metrics token; it never sends that token to the browser. See [the frontend API integration map](frontend/docs/API_INTEGRATION_MAP.md) for endpoint contracts and unavailable metrics.

Run frontend checks from `frontend/` with `npm run typecheck`, `npm test`, `npm run build`, and `npm audit --audit-level=high`. These checks are also configured in the frontend CI job.

## API client credentials

For the API running in Docker Compose, create credentials inside the API container so the credential is written to the same PostgreSQL database that the API uses:

```powershell
docker compose exec -T api python manage.py client_credentials create --name "local-demo"
```

The command prints a bearer token once. In Swagger's **Authorize** dialog, paste the full `CLIENT_UUID.SECRET` token without adding `Bearer`; Swagger adds that prefix to the request. Store the token securely because the database stores only its hash, so it cannot be retrieved later. Tokens do not expire automatically; rotation invalidates the previous secret, and revocation immediately disables the client.

Rotate an exposed or lost token in the same environment where the API is running:

```powershell
docker compose exec -T api python manage.py client_credentials rotate --client-id <CLIENT_UUID>
```

If running Django directly on the host instead of using the Compose API, use `python manage.py client_credentials ...` only when the host process and command use the same `DATABASE_URL`. Compose PostgreSQL is exposed to the host on port `5433` by default, while containers connect to `db:5432`. Creating a credential in a different database from the API causes `401 Unauthorized`.

## Event API

M1 currently accepts the `order.created` event type at schema version `1`. Its payload requires `order_id`, a three-letter uppercase `currency`, non-negative `total_minor_units`, and at least one item with `sku` and positive `quantity`. Timestamps must include a timezone offset. Requests are limited to 256 KiB and batches to 50 events.

Submit an event with `POST /api/v1/events` and `Authorization: Bearer <CLIENT_UUID>.<SECRET>`. A newly accepted event returns `201`; reusing the same client, source, and idempotency key returns `200` with the original event and workflow IDs and `duplicate: true`, even if the replay body has changed. The original event remains unchanged; use a new key for a distinct event. The database uniqueness constraint is authoritative, including under concurrent requests.

`POST /api/v1/events/batch` accepts `{"events": [...]}`. A batch is all-or-nothing: validation or persistence failure rolls back the full batch. Successful batches return each event’s IDs and duplicate flag. The request writes the Kafka handoff into the PostgreSQL outbox in the same transaction. A separate publisher sends it to Kafka after commit.

Use `GET /api/v1/events/{event_id}`, `GET /api/v1/workflows/{workflow_id}`, and `GET /api/v1/workflows?state=RECEIVED` to inspect records belonging to the authenticated client. Workflow listing is paginated at 50 items per page. API errors use an `error` object with a stable code and request ID. Responses also include the `X-Request-ID` header.

## Docker Compose

If `.env` does not exist, copy `.env.example` to `.env`; otherwise merge the documented variables without replacing your existing values. Set a strong local `RABBITMQ_PASSWORD` before the first broker start, then run:

```sh
docker compose up --build
```

Compose starts PostgreSQL, a single-node KRaft Kafka broker, RabbitMQ, ClickHouse, the API, an outbox publisher, a Kafka-to-Rabbit consumer, a workflow worker, and a lifecycle analytics consumer. ClickHouse's Compose credentials default to a local-only development value; override them in `.env` for a shared development machine. Ports bind to localhost. To stop the stack, run `docker compose down`; this preserves database and broker volumes. Do not use `-v` unless you intentionally want to delete local data.

RabbitMQ reads `RABBITMQ_DEFAULT_PASS` only when its data volume is initialized. If you change `RABBITMQ_PASSWORD` later, update the existing RabbitMQ user's password as well; changing `.env` alone does not rotate a credential already stored in the volume. The live RabbitMQ integration test uses the same `RABBITMQ_HOST`, `RABBITMQ_USERNAME`, `RABBITMQ_PASSWORD`, TLS, and CA settings as the application, and fails with a configuration message if those credentials do not match the running broker.

Inspect services and brokers:

```sh
docker compose ps
docker compose exec kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server kafka:9092 --list
docker compose exec rabbitmq rabbitmqctl list_queues name messages consumers
python manage.py outbox_status --check
```

RabbitMQ's management UI is available at `http://localhost:15672` using the local `.env` credentials. Kafka topics are explicitly created by `kafka-init`; the domain and lifecycle topics use three partitions. The local RabbitMQ topology uses quorum queues with a single replica and is for development only.

## M3 ClickHouse lifecycle analytics

`docker/clickhouse/init/001-workflow-lifecycle.sql` creates `eventflow.workflow_lifecycle_facts`, a monthly-partitioned `ReplacingMergeTree` ordered by event date, workflow, event time, and deterministic lifecycle ID. Terminal lifecycle records include stage attempt duration; older v1 lifecycle records without duration remain readable and have a NULL latency. Workflow lifecycle event time is `recorded_at`; measured latency is the individual stage attempt duration, not total end-to-end workflow time.

The analytics process consumes `eventflow.workflow.lifecycle.v1` in the independent `eventflow.clickhouse-analytics.v1` consumer group and commits Kafka offsets only after ClickHouse confirms the insert. If ClickHouse is unavailable, the current offset is left uncommitted and retried with capped exponential wait; Kafka retains the durable replay point. This is at-least-once delivery, not cross-system exactly-once. A deterministic lifecycle ID plus `ReplacingMergeTree` makes duplicate inserts logically idempotent; analytics reads use `FINAL` for immediate query-time deduplication because background merges are eventual. [ClickHouse documents that ReplacingMergeTree merges are asynchronous and recommends `FINAL` when query-time deduplication is required](https://clickhouse.com/resources/engineering/clickhouse-optimize-table-final). PostgreSQL remains the source of truth for current workflow state, and ClickHouse can lag behind it.

You do **not** need to install or create a second database server. Compose runs a separate ClickHouse service and creates the logical `eventflow` database and lifecycle table automatically. It is separate from PostgreSQL because ClickHouse is an analytics store; PostgreSQL remains the transactional source of truth. The `clickhouse_data` Docker volume preserves analytics data.

The Compose application containers connect using `CLICKHOUSE_HOST=clickhouse`; a Django command run from your Windows host connects through `localhost:8123`. Add these values to the existing project `.env` (do not replace the rest of your file). The password below matches the local-only default used by Compose when the ClickHouse volume was first initialized:

```dotenv
CLICKHOUSE_HOST=localhost
CLICKHOUSE_PORT=8123
CLICKHOUSE_DATABASE=eventflow
CLICKHOUSE_USERNAME=eventflow
CLICKHOUSE_PASSWORD=eventflow-local-only
CLICKHOUSE_SECURE=false
CLICKHOUSE_CONNECT_TIMEOUT=3
CLICKHOUSE_SEND_RECEIVE_TIMEOUT=5
```

This password is only for an isolated local development stack; set a unique secret and TLS endpoint for production. ClickHouse stores its initialized user in its volume, so changing `CLICKHOUSE_PASSWORD` in `.env` later does not itself rotate the password inside an already initialized ClickHouse volume. Keep the `.env` value in sync with the currently configured ClickHouse user or perform a deliberate ClickHouse user-password rotation.

After `docker compose up -d --build`, verify the ClickHouse table and inspect the projected metrics (bounded to at most 367 days):

```powershell
docker compose ps
docker compose exec clickhouse clickhouse-client --user eventflow --password eventflow-local-only --query "SHOW TABLES FROM eventflow"
python manage.py analytics_report --from 2026-01-01 --to 2026-12-31
```

The report includes terminal outcomes per minute, success/failure rate, p50/p95/p99 stage-attempt latency, retry counts per workflow, frequent error codes, failure rate by stage, and the oldest/latest projected event timestamp. The table-inspection command uses the local-only default password; if you use another local value, pass that value to `clickhouse-client`. Set `EVENTFLOW_RUN_CLICKHOUSE_INTEGRATION=1` and run `pytest -m integration apps/analytics/tests` with the Compose ClickHouse service available to run the real seeded-data check. Unit tests cover field mapping, deterministic identity, and offset non-commit when ClickHouse fails.

## M4 Evidence-grounded incident assistant

`POST /api/v1/workflows/{workflow_id}/incident-summary` creates and persists an analysis for a failed or dead-lettered workflow owned by the authenticated API client. It is rate-limited per client using a PostgreSQL-backed one-hour window. Production defaults to five requests per hour; local development defaults to 30 requests per hour to allow Swagger iteration (`INCIDENT_SUMMARY_RATE_LIMIT` can override the local value up to 100). Select `INCIDENT_LLM_PROVIDER=gemini` and configure `GEMINI_API_KEY` plus `GEMINI_MODEL` to use Google Gemini; the low-latency default is `gemini-3.5-flash-lite`. If the configured model times out, the adapter makes one bounded failover request to `GEMINI_FALLBACK_MODEL` (defaults to `gemini-3.5-flash-lite`); it never switches to the mock provider. The adapter uses structured JSON output and validates all evidence citations before persistence. `INCIDENT_LLM_PROVIDER=openai` uses `OPENAI_API_KEY` and `OPENAI_MODEL`. Local development defaults to the deterministic `mock` provider unless changed in `.env`. Automated tests always use the mock and do not need provider credentials.

The evidence builder uses a 24-hour window, at most 20 attempts, at most 18 logs, 40 total items, and short sanitized text. It never includes event payloads or arbitrary log attributes. Health metrics are currently reported as unavailable because M1–M3 do not provide workflow-correlated health measurements. Each summary stores the evidence snapshot and SHA-256 hash, prompt version, provider/model, token usage when reported, latency, and creation time. PostgreSQL remains authoritative; an assistant summary is an explanation, not a workflow state transition. Provider retry is capped, and provider errors return safe API errors without persisting a partial summary.

The OpenAI adapter uses strict structured output, disables tools and provider-side storage, and applies a response-size cap. The Gemini adapter uses `generateContent` structured JSON output, sends its API key in the `x-goog-api-key` header, omits tool configuration, and applies the same timeout, output-token, and response-size limits. Provider calls default to a 45-second socket timeout, two total attempts, and a 120-second Gunicorn worker timeout; configuration validation prevents a provider timeout/retry budget above 100 seconds. Both adapters apply bounded retries only to transient failures. Evidence text is untrusted input and is never allowed to act as instructions. All factual claims and hypotheses must cite IDs from supplied evidence; application validation rejects unknown IDs, malformed structures, and an unmarked insufficient-evidence response. The assistant cannot run SQL or commands, publish messages, replay work, or mutate workflow state. See [OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs) and [Gemini structured outputs](https://ai.google.dev/gemini-api/docs/generate-content/structured-output) for provider constrained JSON behavior.

Example evidence-grounded incident:

```json
{
  "headline": "The workflow recorded timeout failures; the underlying cause remains unconfirmed.",
  "confirmed_facts": [
    {"statement": "Workflow state is DEAD_LETTERED at order_validation.", "evidence_ids": ["workflow:timeout"]},
    {"statement": "Two recorded attempts ended with WORKER_TIMEOUT.", "evidence_ids": ["attempt:timeout-a1", "attempt:timeout-a2"]}
  ],
  "hypotheses": [
    {"statement": "A recurring timeout condition likely contributed, but the available records do not identify its source.", "evidence_ids": ["attempt:timeout-a1", "attempt:timeout-a2"], "confidence": 0.75}
  ],
  "unknowns": ["The cause of the timeouts is not established.", "Workflow-correlated dependency health metrics are unavailable."],
  "recommended_checks": ["Review worker and dependency telemetry around the cited attempt timestamps."],
  "insufficient_evidence": false
}
```

The workflow state is supported by `workflow:timeout`; the timeout pattern by the two cited attempt records. The cause stays a hypothesis because neither attempt proves which component caused the timeout. The missing telemetry statement is supported by the health-metrics availability item in the saved evidence snapshot. For automated evaluation, the labeled dataset is in `apps/incidents/tests/fixtures/labeled_incidents.json`; it covers repeated timeouts, invalid business data, worker crash, insufficient evidence, and prompt-injection-like log text.

## Health endpoints

- `GET /health/live` returns `200 {"status":"ok"}` when the process can serve requests. It does not query PostgreSQL.
- `GET /health/ready` runs a short-timeout PostgreSQL query and returns `200 {"status":"ready","checks":{"database":"ok"}}` when available, or `503 {"status":"not_ready","checks":{"database":"unavailable"}}` otherwise.

## M5 observability and operations

JSON logs include request/trace, event, workflow, and correlation IDs when available. The request ID is propagated through the PostgreSQL outbox, Kafka event, RabbitMQ task, and lifecycle message; older messages without this optional field remain accepted. `X-Trace-ID` is a cross-service correlation ID, not an exported OpenTelemetry span.

`GET /metrics` exposes Prometheus text metrics for HTTP traffic, outbox backlog, workflow attempts/retries/dead letters, RabbitMQ ready-queue depth, analytics delivery, and incident-provider latency/errors. Queue depth is sampled by the worker and reports `-1` when unavailable. Compose exposes worker metrics on localhost ports 9101–9104. Set `METRICS_TOKEN` in production; the endpoint requires it in `X-Metrics-Token`. Production settings refuse to start without a metrics token of at least 32 characters.

Dependencies are pinned in `uv.lock`; Docker and CI use `uv sync --frozen`. CI runs Ruff, Django/migration checks, unit/API tests, PostgreSQL concurrency and broker/ClickHouse integration tests, `pip-audit`, and a Trivy image scan. See [the security checklist](docs/security-checklist.md) and [operations runbook](docs/operations-runbook.md) for least-privilege review, metrics interpretation, recovery steps, and the five failure drills.

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
