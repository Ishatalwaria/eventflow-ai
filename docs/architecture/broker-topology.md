# Broker Topology and Message Delivery Semantics

EventFlow AI utilizes a dual-broker architecture combining **Apache Kafka** for durable, partitioned event streaming and **RabbitMQ** for flexible, low-latency, point-to-point task queues with exponential retry and dead-letter handling.

---

## Topology Architecture

```text
PostgreSQL Transaction
  Event + Initial Workflow + ProcessingLog + OutboxMessage
       │
       ▼
Outbox Publisher (SELECT ... FOR UPDATE SKIP LOCKED)
       │ (key=event_id)
       ▼
Kafka Topic: eventflow.domain.events.v1
       │
       ▼
Consumer Group: eventflow.kafka-to-rabbit.v1
       │
       ▼ Publisher-confirmed, persistent task delivery
RabbitMQ Direct Exchange: eventflow.tasks.x
  workflow.stage.v1 ──> Queue: eventflow.tasks.workflow.q
                            │
                            ├── On Transient Failure (Bounded Retries)
                            │     └──> eventflow.retry.x ──> TTL Retry Queues
                            │                                  │ (TTL expired)
                            │                                  └──> task exchange
                            │
                            └── On Permanent Failure / Exhausted Retries
                                  └──> eventflow.dead.x ──> eventflow.tasks.dead.q (DLQ)
                                              │
                                              ▼
Workflow Worker
  PostgreSQL Transaction:
    Workflow State + WorkflowAttempt + ProcessingLog + Lifecycle OutboxMessage
       │
       ▼
Outbox Publisher
       │ (key=workflow_id)
       ▼
Kafka Topic: eventflow.workflow.lifecycle.v1
       │
       ▼
Consumer Group: eventflow.clickhouse-analytics.v1
       │
       ▼ Idempotent batch insertion
ClickHouse Table: eventflow.workflow_lifecycle_facts (ReplacingMergeTree)
```

---

## Message Contracts & Schemas

### 1. Domain Event Contract (`eventflow.domain.events.v1`)
The domain event envelope encapsulates newly accepted business events.
- **Envelope Fields:**
  - `event_id` (UUID string): Unique identifier for the event.
  - `event_type` (string): E.g., `order.created`.
  - `schema_version` (integer): Version identifier (e.g., `1`).
  - `correlation_id` (string): Cross-service trace/correlation identifier.
  - `occurred_at` (ISO 8601 string): Producer event generation timestamp.
  - `recorded_at` (ISO 8601 string): Database ingestion timestamp.
  - `payload` (JSON object): Validated domain payload (e.g., order ID, items, currency).

### 2. Workflow Lifecycle Contract (`eventflow.workflow.lifecycle.v1`)
Lifecycle events capture state transitions and attempt outcomes.
- **Envelope Fields:**
  - `event_id` (UUID string): Correlated ingestion event ID.
  - `workflow_id` (UUID string): Associated workflow identifier.
  - `event_type` (string): State change indicator (`workflow.processing`, `workflow.retry_wait`, `workflow.succeeded`, `workflow.failed`, `workflow.dead_lettered`).
  - `schema_version` (integer): Lifecycle schema version.
  - `correlation_id` (string): Trace correlation identifier.
  - `occurred_at` (ISO 8601 string): State change occurrence time.
  - `recorded_at` (ISO 8601 string): Event recording time.
  - `payload` (JSON object): Attempt number, stage name, duration in milliseconds, error code, and error details.

---

## Ordering, Delivery & Idempotency Guarantees

### Partition Keying
- Kafka records use `event_id` or `workflow_id` as the message key. This guarantees strict partition ordering for all messages related to a single business entity when topic partition counts and hashing remain stable.

### Transactional Outbox Guarantees
- The outbox publisher uses short database transactions with `SELECT ... FOR UPDATE SKIP LOCKED` to acquire a lease on unpublished messages.
- Messages are published to Kafka outside the database transaction.
- Only upon receiving synchronous broker acknowledgment does the publisher mark the outbox row as published.
- *At-Least-Once Delivery:* A node crash occurring after broker acknowledgment but before the database status update can result in message republishing upon lease expiration.

### Kafka to RabbitMQ Bridge
- Auto-commit is disabled on the Kafka consumer.
- The forwarder translates Kafka messages into RabbitMQ tasks and requests publisher confirmations.
- Offsets are committed back to Kafka only after RabbitMQ confirms durable persistence on disk.
- If a forwarder crashes prior to offset commit, the task may be republished to RabbitMQ.

### Worker Task Execution Idempotency
- RabbitMQ task IDs are deterministically derived from the workflow ID and attempt number.
- The worker executes inside an isolated PostgreSQL transaction using row locks (`SELECT ... FOR UPDATE`) and relies on the unique constraint `(workflow_id, stage, attempt_number)`.
- If a worker crashes after committing to PostgreSQL but before sending an ACK to RabbitMQ, RabbitMQ redelivers the message. Upon redelivery, the worker inspects the database, detects the already-committed attempt, and immediately ACKs the duplicate task without repeating the business logic or corrupting state.

### Bounded Retries & Dead-Letter Queue (DLQ)
- Transient exceptions (e.g., temporary lock contention or network timeouts) trigger bounded retries routed to TTL queues under `eventflow.retry.x`. When TTL expires, the messages re-enter `eventflow.tasks.x`.
- Permanent failures (e.g., domain validation failure or out-of-stock condition) or exhausted retries are recorded with terminal states (`FAILED` or `DEAD_LETTERED`) in PostgreSQL and published to `eventflow.tasks.dead.q` for operational inspection.

### ClickHouse Analytics Delivery
- The ClickHouse analytics consumer maintains an independent Kafka consumer group (`eventflow.clickhouse-analytics.v1`).
- Offsets are committed only after ClickHouse confirms the batch insert.
- Deduplication is handled transparently through ClickHouse's `ReplacingMergeTree` keyed on `(event_date, workflow_id, recorded_at, lifecycle_id)` combined with query-time `FINAL` operators.

---

## Operational Monitoring & Inspection

- **Outbox Backlog:** Monitor via `python manage.py outbox_status --check` or Prometheus gauge `eventflow_outbox_unpublished_messages`.
- **Queue Depths:** Inspect queue status with `rabbitmqctl list_queues name messages consumers` or the Prometheus gauge `eventflow_rabbitmq_queue_messages`.
- **Kafka Topics:** Inspect active topic configurations with `kafka-topics.sh --bootstrap-server kafka:9092 --list`.
