# M2 broker topology and delivery semantics

## Topology

```text
PostgreSQL transaction
  Event + initial Workflow + ProcessingLog + domain OutboxMessage
       |
       v
Outbox publisher --(key=event_id)--> Kafka: eventflow.domain.events.v1
                                         |
                                         v
                              consumer group:
                              eventflow.kafka-to-rabbit.v1
                                         |
                         publisher-confirmed, persistent task
                                         v
RabbitMQ direct exchange: eventflow.tasks.x
  order.created.v1 -> eventflow.tasks.order-validation.q
                           | transient error, bounded attempts
                           +--> eventflow.retry.x -> TTL retry queues
                           |                        -> task exchange
                           +--> eventflow.dead.x -> eventflow.tasks.dead.q
                                         |
                                         v
                              workflow worker
  PostgreSQL transaction: Workflow + WorkflowAttempt + ProcessingLog
                          + lifecycle OutboxMessage
       |
       +---- outbox publisher --> Kafka: eventflow.workflow.lifecycle.v1
```

## Message contracts

The domain topic contains the accepted event envelope. Its `event_type` and
`schema_version` describe the event contract. The envelope has `event_id`,
`event_type`, `schema_version`, `correlation_id`, `occurred_at`,
`recorded_at`, and a bounded JSON `payload`. The lifecycle topic uses
`event_type` values such as `workflow.processing`, `workflow.retry_wait`,
`workflow.succeeded`, `workflow.failed`, and `workflow.dead_lettered`; its
schema version is independently versioned. Lifecycle messages include
`event_id`, `workflow_id`, `schema_version`, `correlation_id`, `occurred_at`,
`recorded_at`, and a small state/attempt payload. Both topics are configured
explicitly; topic creation is not delegated to auto-topic creation.
Compose also creates the isolated `eventflow.integration.events.v1` topic used
by real-broker adapter tests. The application consumer group does not subscribe
to that topic, so test records cannot become invalid domain events.

## Ordering and delivery

- Kafka records use `event_id` as the key. This preserves partition order for
  one event when Kafka partition count and the partitioner remain stable. It
  does not order different events or provide a global order.
- The outbox publisher uses a short PostgreSQL transaction to lease rows with
  `SELECT ... FOR UPDATE SKIP LOCKED`, then publishes outside that transaction.
  It records publication only after Kafka confirms delivery. A crash after
  broker acceptance and before that database update can publish the record
  again after lease expiry.
- Kafka consumer auto-commit is disabled. The consumer waits for RabbitMQ's
  publisher confirm on a durable, persistent task publish before committing
  the Kafka offset synchronously. A crash between those operations can enqueue
  the task twice. Broker handoff is at-least-once, not exactly-once.
- RabbitMQ task IDs are deterministic from the workflow ID and processing
  attempt. The worker uses PostgreSQL row locks and the unique
  `(workflow, stage, attempt_number)` constraint to make duplicate task
  delivery safe. It commits workflow, attempt, processing log, and lifecycle
  outbox changes together, then acknowledges the RabbitMQ delivery.
- If the worker crashes after that commit and before its acknowledgement,
  RabbitMQ redelivers. A terminal workflow or already-recorded attempt is
  recognized and acknowledged without repeating the database transition.
- Retry delays are finite and configured on durable TTL queues. Transient
  failures are republished with confirms to the next retry route before the
  original delivery is acknowledged. Permanent business failures and exhausted
  transient failures are recorded in PostgreSQL and routed to a durable DLQ.
  Retry/DLQ messages can themselves be duplicated, so their task IDs and
  database effects remain idempotent.
- A broker outage leaves PostgreSQL outbox rows unpublished or leaves Kafka
  offsets uncommitted. Both conditions are retried after bounded waits; no
  broker call is made inside a PostgreSQL transaction.

## Operations

The oldest-unpublished-outbox age and count are available through the
`outbox_status` management command. Alert when the oldest row exceeds the
configured operational threshold. Inspect Kafka topics and RabbitMQ queues
using the documented Compose commands; do not infer successful processing
from a producer call alone.
