# EventFlow AI — interview notes

## Why this project exists

EventFlow is a portfolio system for reliable order fulfillment. It shows how to accept a business event once, process it through explicit stages, and recover when a later stage fails.

## Business problem

An order must reserve stock, authorize payment, and confirm shipment without overselling or charging twice. If payment fails after stock is reserved, the reservation has to be released exactly once.

## Why Kafka and RabbitMQ

Kafka stores the durable domain and lifecycle stream. RabbitMQ runs the work: bounded retries, TTL backoff, and a dead-letter queue. The API writes to PostgreSQL only. A transactional outbox publishes to Kafka. A forwarder turns that into a Rabbit task after the broker confirms the publish.

## How the saga works

Workflow definitions list stages and which stages have a compensation. The worker runs one stage per message. A successful non-final stage enqueues the next stage. A permanent failure after a reserving stage enqueues `release_inventory`, then marks the workflow failed. State changes and attempt rows are committed in PostgreSQL before the next message is published.

## Compensation

`release_inventory` is a normal stage with `direction=compensate`. Its idempotency key is the reservation id. A redelivered compensation message sees the existing movement and does not release stock again.

## Duplicate events

Ingestion is unique on `(client, source, idempotency_key)`. A replay returns the original event. Stage attempts are unique on `(workflow, stage, direction, attempt_number)`, so a redelivered task does not run the business action twice.

## Concurrency

Inventory rows are locked with `SELECT FOR UPDATE`. Available quantity is `on_hand - reserved`. A second reservation that would exceed available stock raises `INSUFFICIENT_INVENTORY`.

## Failure recovery

Transient stage errors retry on the Rabbit TTL queues until `WORKER_MAX_ATTEMPTS`. Exhausted retries are dead-lettered. Operators can retry or replay a failed workflow through an audited API. Those actions enqueue the failed stage again; they do not update stock or payment rows directly.

## Trade-offs

One worker process runs every stage. That is simpler than a service per stage and still exercises the outbox, brokers, and saga. Payment is a local simulator so the failure paths are deterministic. Replenishment approval is an `approval_token` on the event, not a human task inbox.

## Still incomplete

There is no real payment provider, no OpenTelemetry export, and no separate HTTP health port on the workers. ClickHouse is the analytics projection; PostgreSQL remains the source of truth for orders, inventory, payments, and workflow state.
