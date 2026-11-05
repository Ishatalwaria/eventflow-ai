# EventFlow AI — Architecture Documentation Index

Welcome to the technical architecture documentation for **EventFlow AI** — an event-driven workflow orchestration and operational intelligence platform.

This directory contains 10 verified architecture diagrams and technical specifications detailing the system's design, component boundaries, asynchronous message pipelines, failure resilience, and analytical/AI layers.

---

## Architecture Diagram Map

| Diagram | Document | Focus Area | Key Technologies | Implementation Status |
| :--- | :--- | :--- | :--- | :--- |
| **01** | [System Architecture](01-system-architecture.md) | High-level platform topology and tier boundaries | Django, Kafka, RabbitMQ, Postgres, ClickHouse | **Implemented & Verified** |
| **02** | [Event Ingestion & Outbox](02-event-ingestion-outbox.md) | Ingestion atomicity, idempotency, and transactional outbox | DRF, PostgreSQL ACID, `SELECT FOR UPDATE SKIP LOCKED` | **Implemented & Verified** |
| **03** | [Kafka to RabbitMQ Pipeline](03-kafka-rabbitmq-pipeline.md) | Broker streaming, bridge consumer, task dispatching | Apache Kafka (KRaft), RabbitMQ Direct Exchanges | **Implemented & Verified** |
| **04** | [Workflow Lifecycle & Sagas](04-workflow-lifecycle.md) | State machine, forward stages, and backward compensation | Python Saga Engine, Order Fulfillment, Replenishment | **Implemented & Verified** |
| **05** | [Retry & Dead-Letter Flow](05-retry-and-dead-letter.md) | Transient retry routing, TTL delay queues, DLQ triage | RabbitMQ Dead-Lettering, Operator Interventions | **Implemented & Verified** |
| **06** | [Analytics & ClickHouse Data Flow](06-analytics-clickhouse.md) | Event projection, analytical OLAP facts, query boundaries | ClickHouse `ReplacingMergeTree`, Kafka Consumer Group | **Implemented & Verified** |
| **07** | [AI Operational Intelligence](07-ai-operational-intelligence.md) | Evidence collection, PII redaction, LLM incident root-cause | Gemini 3.8 Flash, OpenAI GPT-4.1-mini, Mock Provider | **Implemented & Verified** |
| **08** | [Authentication & Security](08-authentication-flow.md) | API client tokens, session auth, tenant isolation filters | PBKDF2 Bearer Tokens, Django Sessions, Query Scoping | **Implemented & Verified** |
| **09** | [Deployment & Infrastructure](09-deployment-architecture.md) | Docker Compose services, networks, volumes, K8s roadmap | Docker Compose (9 Services), Planned Kubernetes Spec | **Implemented (Compose) / Planned (K8s)** |
| **10** | [End-to-End Event Lifecycle](10-end-to-end-event-lifecycle.md) | Sequence flow from HTTP client ingress to UI completion | End-to-end execution, compensation, and analytics sync | **Implemented & Verified** |

---

## System Overview & Core Invariants

EventFlow AI is engineered around the following core architectural invariants:

1. **Guaranteed Event Ingestion via Transactional Outbox**:
   The ingestion API never publishes directly to external message brokers within an HTTP request. Instead, it writes the domain `Event`, initial `Workflow`, initial `ProcessingLog`, and `OutboxMessage` inside a single PostgreSQL ACID transaction. This eliminates dual-write hazards and prevents lost events.

2. **Dual-Broker Decoupled Pipeline**:
   - **Apache Kafka** serves as the immutable, high-throughput distributed commit log (`eventflow.domain.events.v1` and `eventflow.workflow.lifecycle.v1`).
   - **RabbitMQ** serves as the low-latency, point-to-point task queue (`eventflow.tasks.workflow.q`) supporting message acknowledgements, backoff TTL routing (`retry.5s`, `retry.30s`), and dead-letter queues (`eventflow.tasks.dead.q`).

3. **Orchestration Saga Engine with Compensation**:
   Complex business flows (e.g., Order Fulfillment: `validate_order` ➔ `reserve_inventory` ➔ `authorize_payment` ➔ `confirm_order` ➔ `prepare_shipment` ➔ `notify`) are executed stage-by-stage. Reversible actions (such as inventory reservation) register discrete compensation handlers (`release_inventory`) executed in LIFO order upon permanent failure.

4. **Dual-Storage Analytics Separation (OLTP vs OLAP)**:
   - **PostgreSQL**: Manages active tenant data, mutable saga state machines, idempotency locks, and operator audit logs.
   - **ClickHouse**: Ingests immutable lifecycle facts via Kafka consumer for high-velocity aggregations (p50/p95/p99 latencies, per-minute throughput, error distributions) without impacting relational database lock performance.

5. **Grounded, Read-Only AI Incident Intelligence**:
   The AI operational analysis engine gathers bounded, deterministic evidence (sanitized event payloads, discrete attempt records, structured log entries), strips PII/secrets, and prompts LLMs (Gemini / OpenAI) for structured root-cause explanations and operator recommendations. The AI system has **zero write permissions** on workflow state or business data.

---

## Verified Codebase Locations

- **API & Authentication**: [`apps/events/`](file:///d:/eventflow-ai/apps/events), [`apps/common/`](file:///d:/eventflow-ai/apps/common)
- **Saga Engine & State Machine**: [`apps/processing/saga/`](file:///d:/eventflow-ai/apps/processing/saga), [`apps/workflows/`](file:///d:/eventflow-ai/apps/workflows)
- **Brokers & Outbox Workers**: [`apps/processing/`](file:///d:/eventflow-ai/apps/processing)
- **Commerce Domain**: [`apps/commerce/`](file:///d:/eventflow-ai/apps/commerce)
- **Analytics & ClickHouse**: [`apps/analytics/`](file:///d:/eventflow-ai/apps/analytics), [`docker/clickhouse/init/`](file:///d:/eventflow-ai/docker/clickhouse/init)
- **AI Operational Intelligence**: [`apps/incidents/`](file:///d:/eventflow-ai/apps/incidents)
- **Frontend Dashboard**: [`frontend/src/`](file:///d:/eventflow-ai/frontend/src)
- **Docker Compose Topology**: [`docker-compose.yml`](file:///d:/eventflow-ai/docker-compose.yml)

