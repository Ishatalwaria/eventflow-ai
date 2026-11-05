# EventFlow AI

[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/)
[![Django 6.1](https://img.shields.io/badge/django-6.1-green.svg)](https://www.djangoproject.com/)
[![React 19](https://img.shields.io/badge/react-19-61dafb.svg)](https://react.dev/)
[![Kafka](https://img.shields.io/badge/Apache_Kafka-3.9-black.svg)](https://kafka.apache.org/)
[![RabbitMQ](https://img.shields.io/badge/RabbitMQ-3.13-orange.svg)](https://www.rabbitmq.com/)
[![ClickHouse](https://img.shields.io/badge/ClickHouse-24.8-yellow.svg)](https://clickhouse.com/)
[![License](https://img.shields.io/badge/license-Proprietary-lightgrey.svg)](#project-notice--licensing)

**EventFlow AI** is a production-grade, event-driven workflow orchestration and operational intelligence platform. It combines transactional event ingestion, guaranteed at-least-once message delivery via a PostgreSQL transactional outbox, dual-broker routing (Apache Kafka + RabbitMQ), real-time lifecycle analytics in ClickHouse, and an evidence-grounded AI incident investigation engine.

---

## Architecture Overview

```text
PostgreSQL Transaction (Source of Truth)
  Event + Initial Workflow + ProcessingLog + OutboxMessage
       │
       ▼
Outbox Publisher (SELECT ... FOR UPDATE SKIP LOCKED)
       │ (key=event_id)
       ▼
Kafka Topic: eventflow.domain.events.v1
       │
       ▼
Kafka-to-Rabbit Forwarder (Consumer Group: eventflow.kafka-to-rabbit.v1)
       │ (publisher-confirmed)
       ▼
RabbitMQ Direct Exchange: eventflow.tasks.x
  workflow.stage.v1 ──> Queue: eventflow.tasks.workflow.q
                            │
                            ├── On Transient Failure ──> eventflow.retry.x (TTL queues)
                            │                                  │ (TTL expired)
                            │                                  └──> task exchange
                            │
                            └── On Permanent Failure ──> eventflow.dead.x (DLQ)
                                                              │
                                                              ▼
Workflow Worker
  PostgreSQL Transaction:
    Workflow State + WorkflowAttempt + ProcessingLog + Lifecycle OutboxMessage
       │
       ▼
Outbox Publisher ──> Kafka Topic: eventflow.workflow.lifecycle.v1
                          │
                          ▼
ClickHouse Analytics Consumer ──> ClickHouse Table: workflow_lifecycle_facts
```

For complete technical specifications, see:
- [Architecture Documentation & Specifications](docs/architecture/README.md)
- [Operations Runbook & Failure Drills](docs/operations-runbook.md)
- [Production Security Checklist](docs/security-checklist.md)

---

## Key Features

- **Transactional Event Ingestion:** Atomic ingestion of events, initial workflow state, and outbox messages within a single PostgreSQL ACID transaction. Uniqueness constraints on `(client_id, source, idempotency_key)` guarantee idempotent ingestion under concurrent retries.
- **Transactional Outbox & Resilient Delivery:** Background publisher leases pending outbox messages using `SELECT ... FOR UPDATE SKIP LOCKED` and publishes to Kafka with synchronous acknowledgment, eliminating distributed dual-write inconsistencies.
- **Dual-Broker Architecture:** High-throughput event streaming via **Apache Kafka** partitioned by entity key, decoupled into **RabbitMQ** quorum queues for low-latency task execution, exponential backoff TTL retries, and dead-letter queueing (DLQ).
- **Dual-Tier Authentication & Multi-Tenancy:**
  - *Human Operators:* Web console session authentication via encrypted, `HttpOnly`, `SameSite=Lax` cookies with native CSRF validation.
  - *Automated Microservices:* Cryptographic Bearer token authentication (`<CLIENT_UUID>.<SECRET>`) stored using PBKDF2/SHA256 password hashing.
  - *Data Isolation:* Strict tenant-level scoping across events, workflows, incidents, and operational metrics.
- **Real-Time & Lifecycle Analytics:**
  - *Tenant-Scoped (PostgreSQL):* Real-time operational aggregates, processing latency percentiles, and current-state summary metrics.
  - *Platform-Wide (ClickHouse):* High-volume historical lifecycle analytics stored in monthly-partitioned `ReplacingMergeTree` tables with query-time `FINAL` deduplication.
- **Evidence-Grounded AI Incident Assistant:**
  - Automated root-cause investigation for `FAILED` or `DEAD_LETTERED` workflows.
  - Assembles a bounded 24-hour sanitized evidence window (attempts, log codes; zero raw payload data).
  - Integrates with **Google Gemini** (`gemini-3.5-flash-lite` with automatic fallback), **OpenAI** (`gpt-4o-mini`), or a deterministic local mock provider.
  - Enforces strict structured output validation: all claims and hypotheses must cite verifiable evidence IDs from the supplied context.
  - Strictly read-only: the assistant cannot mutate state, replay events, or execute commands.
- **Comprehensive Observability:**
  - Contextual structured JSON logs with propagated `request_id`, `trace_id`, `event_id`, and `workflow_id`.
  - Prometheus `/metrics` text exposition endpoint protected by an operational token (`X-Metrics-Token`).
  - Liveness (`/health/live`), database readiness (`/health/ready`), and multi-service component probes (`/health/services`).
- **Modern Web Operations Console:** Built with React 19, TypeScript, Vite, and Tailwind CSS. Features full event exploration, workflow timeline tracking, interactive incident investigation, and in-console API client credential management.

---

## Technology Stack

| Layer | Technologies |
|---|---|
| **Backend Framework** | Python 3.12, Django 6.1, Django REST Framework, drf-spectacular (OpenAPI 3.0.3) |
| **Primary Database** | PostgreSQL 16 (Transactional source of truth, Outbox, Identity, Workflows) |
| **Event Streaming** | Apache Kafka 3.9 (KRaft mode, durable domain and lifecycle event topics) |
| **Task Queue & Broker** | RabbitMQ 3.13 (Quorum task queues, TTL retry queues, Dead-letter exchange) |
| **Analytics Engine** | ClickHouse 24.8 (`ReplacingMergeTree`, high-throughput lifecycle aggregation) |
| **AI / LLM Integration** | Google Gemini API (`gemini-3.5-flash-lite`), OpenAI API (`gpt-4o-mini`), Mock provider |
| **Frontend Console** | React 19, TypeScript, Vite 7, Tailwind CSS 3, TanStack Query v5, Recharts |
| **Packaging & Runtime** | uv 0.13.6, Docker Engine, Docker Compose v2, Gunicorn |

---

## Repository Structure

```text
eventflow-ai/
├── apps/                        # Django modular applications
│   ├── analytics/               # ClickHouse sink, migrations, queries, and reports
│   ├── common/                  # Dual auth, middleware, health probes, Prometheus metrics
│   ├── events/                  # Ingestion endpoints, event models, schema validation
│   ├── incidents/               # AI incident assistant, evidence builder, LLM adapters
│   ├── processing/              # Outbox publisher, Kafka consumer, Rabbit worker, retry
│   └── workflows/               # Workflow models, attempt tracking, lifecycle state machine
├── config/                      # Django project configuration
│   ├── settings/                # base, local, production, test, postgres_integration
│   ├── gunicorn.conf.py         # Production WSGI server configuration
│   └── urls.py                  # Root URL routing and OpenAPI schema endpoints
├── docker/                      # Docker assets and initialization scripts
│   ├── clickhouse/init/         # ClickHouse SQL DDL initialization scripts
│   └── kafka/                   # Kafka KRaft topic provisioning scripts
├── docs/                        # Permanent technical documentation
│   ├── architecture/            # System architecture and broker topology specifications
│   ├── operations-runbook.md    # Production operations runbook and recovery drills
│   └── security-checklist.md    # Pre-deployment security verification checklist
├── frontend/                    # React + TypeScript operations console
│   ├── docs/                    # Frontend API integration map and test documentation
│   ├── src/                     # Application source code (components, features, API client)
│   ├── package.json             # Locked npm dependencies and build scripts
│   └── vite.config.ts           # Vite bundler configuration and local dev proxy
├── .env.example                 # Documented environment variable template
├── docker-compose.yml           # Complete multi-container development environment
├── Dockerfile                   # Multi-stage, non-root production container definition
├── pyproject.toml               # Python package metadata, dependencies, and tool settings
├── README.md                    # Flagship project documentation
└── uv.lock                      # Cryptographically pinned Python dependency lockfile
```

---

## Prerequisites

- **Python:** 3.12
- **uv:** 0.13.6 or newer (`pip install uv` or install via standalone installer)
- **Node.js:** 20 LTS or newer with `npm`
- **Docker & Docker Compose:** Docker Compose v2 is required for running the local distributed service stack.

---

## Local Development Setup

### 1. Environment Configuration

Copy the example environment files for both backend and frontend:

```bash
# Backend configuration
cp .env.example .env

# Frontend configuration
cp frontend/.env.example frontend/.env
```

Open `.env` and verify local credentials. The default values are tuned for an isolated local Docker Compose stack.

### 2. Start Full Stack with Docker Compose

To start PostgreSQL, Kafka (KRaft), RabbitMQ, ClickHouse, the Django API, outbox publisher, Kafka forwarder, workflow worker, and analytics consumer:

```bash
docker compose up -d --build
```

Verify service status:

```bash
docker compose ps
```

- **API Base URL:** `http://localhost:8000`
- **Interactive Swagger Documentation:** `http://localhost:8000/api/docs/`
- **Raw OpenAPI Schema:** `http://localhost:8000/api/schema/`
- **RabbitMQ Management UI:** `http://localhost:15672` (credentials from `.env`)

### 3. Start the Frontend Console

In a separate terminal:

```bash
cd frontend
npm ci
npm run dev
```

Open `http://localhost:5173` to access the operations console.

---

## Authentication & Credential Management

EventFlow AI supports two complementary access mechanisms:

### A. Web Console (Human Operators)
1. Navigate to `http://localhost:5173/signup`.
2. Register an account with your name, email, and password.
3. Upon registration, an encrypted `HttpOnly` session cookie is established, and a default API ingestion key is automatically provisioned for your workspace.
4. Manage API keys anytime under **Settings** (`/settings`), where you can provision new client keys or revoke existing ones.

### B. Machine-to-Machine Ingestion (Microservices)
For automated ingestion, provision client credentials directly inside the running API container:

```bash
docker compose exec -T api python manage.py client_credentials create --name "microservice-producer"
```

To grant system-wide ClickHouse analytics read permissions:

```bash
docker compose exec -T api python manage.py client_credentials create --name "analytics-reader" --analytics-access
```

The CLI prints the token **once**:
```text
Client token:
<CLIENT_UUID>.<SECRET>
Store this token now. It cannot be retrieved later.
```

Include this token in all ingestion requests:
```http
Authorization: Bearer <CLIENT_UUID>.<SECRET>
```

To rotate a compromised or exposed token:
```bash
docker compose exec -T api python manage.py client_credentials rotate --client-id <CLIENT_UUID>
```

---

## Event Ingestion & Workflow Execution

### Single Event Ingestion

Submit an authenticated event via `POST /api/v1/events`:

```bash
curl -X POST http://localhost:8000/api/v1/events \
  -H "Authorization: Bearer <CLIENT_UUID>.<SECRET>" \
  -H "Content-Type: application/json" \
  -d '{
    "event_type": "order.created",
    "schema_version": 1,
    "source": "checkout-web",
    "idempotency_key": "order-demo-001",
    "occurred_at": "2026-11-02T10:00:00Z",
    "correlation_id": "corr-demo-001",
    "payload": {
      "order_id": "ORD-1001",
      "currency": "USD",
      "total_minor_units": 24900,
      "items": [
        {"sku": "ITEM-KEYBOARD", "quantity": 1}
      ]
    }
  }'
```

**Responses:**
- `201 Created`: Event accepted, workflow initialized, outbox message scheduled.
- `200 OK`: Idempotent replay detected matching `(client_id, source, idempotency_key)`. Returns original event and workflow IDs with `"duplicate": true`.

### Batch Event Ingestion

`POST /api/v1/events/batch` accepts `{ "events": [...] }` (up to 50 events). The entire batch is processed within an atomic database transaction (all-or-nothing rollback on validation or database failure).

### Inspecting Workflow Progress

```bash
# Query single workflow
curl -H "Authorization: Bearer <TOKEN>" http://localhost:8000/api/v1/workflows/<WORKFLOW_UUID>

# List workflows by state
curl -H "Authorization: Bearer <TOKEN>" "http://localhost:8000/api/v1/workflows?state=SUCCEEDED"
```

---

## AI Incident Investigation

When a workflow enters `FAILED` or `DEAD_LETTERED`, trigger an evidence-grounded AI analysis via `POST /api/v1/workflows/{workflow_id}/incident-summary`:

```bash
curl -X POST http://localhost:8000/api/v1/workflows/<WORKFLOW_UUID>/incident-summary \
  -H "Authorization: Bearer <TOKEN>"
```

### Response Example:
```json
{
  "id": "b3e0cf7c-9b83-4eb3-9a92-25d44a7ab414",
  "workflow_id": "c3b55ac2-99d2-4674-b249-5cb7d4564425",
  "evidence_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
  "summary": {
    "headline": "Workflow failed due to repeated inventory validation timeouts.",
    "confirmed_facts": [
      {
        "statement": "Workflow reached DEAD_LETTERED state at stage order_validation.",
        "evidence_ids": ["workflow:c3b55ac2"]
      },
      {
        "statement": "Attempts 1 and 2 failed with error code WORKER_TIMEOUT.",
        "evidence_ids": ["attempt:c3b55ac2-a1", "attempt:c3b55ac2-a2"]
      }
    ],
    "hypotheses": [
      {
        "statement": "Downstream inventory database connection exhaustion likely exceeded the attempt deadline.",
        "evidence_ids": ["attempt:c3b55ac2-a1", "attempt:c3b55ac2-a2"],
        "confidence": 0.82
      }
    ],
    "unknowns": [
      "Inventory service internal error telemetry was not available in the sanitized evidence window."
    ],
    "recommended_checks": [
      "Review inventory cluster connection pool metrics around attempt timestamps."
    ],
    "insufficient_evidence": false
  },
  "provider": "gemini",
  "model": "gemini-3.5-flash-lite",
  "latency_ms": 1140,
  "created_at": "2026-11-02T10:05:00Z"
}
```

Configurable in `.env`:
- `INCIDENT_LLM_PROVIDER`: `gemini` (default), `openai`, or `mock`.
- `GEMINI_API_KEY`: API key for Google Gemini.
- `GEMINI_MODEL`: Model name (defaults to `gemini-3.5-flash-lite`).
- `GEMINI_FALLBACK_MODEL`: Fallback model name on transient provider failure.

---

## Health & Observability

### Health Probes
- `GET /health/live`: Fast process liveness check (HTTP 200 OK). Does not touch downstream dependencies.
- `GET /health/ready`: PostgreSQL connectivity check. Returns 200 OK when ready or 503 Service Unavailable when database connection fails.
- `GET /health/services`: Authenticated deep probe verifying PostgreSQL, Kafka, RabbitMQ, ClickHouse, and worker metric availability.

### Prometheus Metrics
`GET /metrics` exposes standard Prometheus text metrics. In production, configure `METRICS_TOKEN` (minimum 32 characters) and pass the `X-Metrics-Token` header:

```bash
curl -H "X-Metrics-Token: <METRICS_TOKEN>" http://localhost:8000/metrics
```

Key exposed metrics:
- `eventflow_http_requests_total`: Counts requests partitioned by handler and HTTP status code.
- `eventflow_outbox_unpublished_messages`: Gauge of pending transactional outbox rows awaiting publication.
- `eventflow_outbox_oldest_unpublished_age_seconds`: Age of the oldest unpublished outbox row.
- `eventflow_workflow_attempts_total`: Counter of worker task execution attempts by stage and outcome.
- `eventflow_workflow_retries_total` & `eventflow_workflow_dead_letters_total`: Failure and retry progression.
- `eventflow_rabbitmq_queue_messages`: Depth of task, retry, and dead-letter queues.
- `eventflow_analytics_deliveries_total`: ClickHouse projection ingestions and failures.
- `eventflow_incident_provider_latency_seconds`: Latency distribution of AI provider invocations.

---

## Testing & Quality Assurance

### Backend Test Suite

The default pytest configuration runs against an isolated, fast in-memory SQLite database:

```bash
# Run unit and API tests
uv run pytest

# Check code formatting and linting
uv run ruff check .
uv run ruff format --check .

# Validate Django models and migrations
uv run python manage.py check
```

#### Running Concurrency & Real Broker Integration Tests
With local Compose services running, execute the full integration suite:

```bash
# In Bash:
EVENTFLOW_RUN_BROKER_INTEGRATION=1 EVENTFLOW_RUN_CLICKHOUSE_INTEGRATION=1 uv run pytest -m integration

# In PowerShell:
$env:EVENTFLOW_RUN_BROKER_INTEGRATION = "1"
$env:EVENTFLOW_RUN_CLICKHOUSE_INTEGRATION = "1"
uv run pytest -m integration
```

### Frontend Test Suite

From the `frontend/` directory:

```bash
# Run TypeScript compilation check
npm run typecheck

# Run unit and component tests (Vitest + React Testing Library)
npm test

# Verify production bundle compilation
npm run build

# Run dependency vulnerability audit
npm audit --audit-level=high
```

---

## Production Deployment & Security

When deploying to production, follow the guidelines below and complete the [Production Security Checklist](docs/security-checklist.md):

1. **Environment Settings:**
   - Set `DJANGO_SETTINGS_MODULE=config.settings.production`.
   - Set `DEBUG=false`.
   - Provide explicit, non-wildcard hostnames in `ALLOWED_HOSTS`.
   - Generate a strong, unique `DJANGO_SECRET_KEY` (minimum 50 characters).
2. **Database Role Segregation:**
   - Enforce least privilege by creating two separate database users:
     - `eventflow_migrator`: Owns database schema; executes `python manage.py migrate`.
     - `eventflow_app`: Unprivileged runtime user possessing only `SELECT`, `INSERT`, `UPDATE`, `DELETE` on tables and `USAGE`, `SELECT` on sequences. Must not have `CREATEDB` or `CREATEROLE`.
3. **Mandatory TLS:**
   - PostgreSQL: Use `sslmode=verify-full` with verified CA certificates.
   - Kafka: Configure `KAFKA_SECURITY_PROTOCOL=SSL` or `SASL_SSL`.
   - RabbitMQ: Set `RABBITMQ_USE_TLS=true` with verified broker certificates.
   - ClickHouse: Set `CLICKHOUSE_SECURE=true`.
4. **Container Hardening:**
   - The production container (`Dockerfile`) executes as non-root user `eventflow` (`UID 10001 / GID 10001`).
   - Run migrations in an isolated pre-deployment step using the migration credentials before rolling out API or worker pods.

---

## Project Notice & Licensing

EventFlow AI is a personal proprietary project developed for demonstration and operational workflow orchestration. It is maintained solely for personal use. External contributions, pull requests, and distribution are not accepted.

---

## Known Limitations

- **Event schema support:** Ingestion supports `order.created`, `inventory.replenishment.requested`, and `payment.recovery.requested` (schema version 1). New types need a payload contract and a workflow definition.
- **Payments:** Authorization uses `LocalPaymentSimulator`. Tokens `ok_`, `fail_`, and `timeout_` are deterministic. No card network or real money movement is involved.
- **Orchestrator shape:** One workflow worker runs every stage. Compensation is an explicit saga stage, not a separate service.
- **Trace Context Export:** Structured logging correlates requests using `X-Request-ID` and `X-Trace-ID` across all services, but does not currently export OpenTelemetry distributed trace spans.
- **Worker Process Health:** Worker daemons report health status through process heartbeat and Prometheus metrics; they do not expose standalone HTTP readiness endpoints.
