# Diagram 3: Kafka to RabbitMQ Processing Pipeline

## Purpose
This document explains the messaging architecture and service interactions between **Apache Kafka** and **RabbitMQ** in EventFlow AI. It details why both message systems are utilized, how the bridge consumer guarantees message delivery without loss, and where at-least-once semantics occur.

---

## Dual-Broker Pipeline Diagram

```mermaid
flowchart TD
    %% Styling
    classDef kafkaStyle fill:#ede9fe,stroke:#7c3aed,stroke-width:2px,color:#6d28d9;
    classDef rabbitStyle fill:#ffedd5,stroke:#ea580c,stroke-width:2px,color:#c2410c;
    classDef workerStyle fill:#fae8ff,stroke:#c026d3,stroke-width:2px,color:#a21caf;
    classDef pgStyle fill:#ecfdf5,stroke:#059669,stroke-width:2px,color:#047857;

    subgraph KafkaTier["Layer A: Distributed Streaming (Apache Kafka)"]
        OutboxPub["Outbox Publisher Worker<br/>(publish_outbox.py)"]:::workerStyle
        DomainTopic{{"Topic: eventflow.domain.events.v1<br/>Partitions: 3 | Key: event_id"}}:::kafkaStyle
    end

    subgraph BridgeTier["Layer B: Kafka-to-RabbitMQ Bridge"]
        KafkaBridgeConsumer["Bridge Consumer Process<br/>Group: eventflow.kafka-to-rabbit.v1<br/>(consume_domain_events.py)"]:::workerStyle
    end

    subgraph RabbitTier["Layer C: Task Brokerage & Routing (RabbitMQ)"]
        TaskExchange[["Direct Exchange: eventflow.tasks.x"]]:::rabbitStyle
        TaskQueue["Task Queue: eventflow.tasks.workflow.q<br/>Durable | Prefetch: 10"]:::rabbitStyle
        
        RetryExchange[["Direct Exchange: eventflow.retry.x"]]:::rabbitStyle
        RetryQueue5s["Queue: eventflow.tasks.retry.5s.q<br/>TTL: 5,000ms | x-dead-letter: eventflow.tasks.x"]:::rabbitStyle
        RetryQueue30s["Queue: eventflow.tasks.retry.30s.q<br/>TTL: 30,000ms | x-dead-letter: eventflow.tasks.x"]:::rabbitStyle
        
        DeadExchange[["Direct Exchange: eventflow.dead.x"]]:::rabbitStyle
        DeadQueue["DLQ Queue: eventflow.tasks.dead.q<br/>Durable"]:::rabbitStyle
    end

    subgraph WorkerTier["Layer D: Workflow Execution Engine"]
        WorkflowWorker["Workflow Saga Worker<br/>(process_workflows.py)"]:::workerStyle
    end

    subgraph DatabaseTier["Layer E: Relational Persistence (PostgreSQL)"]
        Postgres[("PostgreSQL 16<br/>workflows, attempts, processing_logs")]:::pgStyle
    end

    %% Pipeline Flow
    OutboxPub -->|"1. Publish Event<br/>(Key=event_id)"| DomainTopic
    DomainTopic -->|"2. Poll Partition Records"| KafkaBridgeConsumer
    
    %% Bridge Logic
    KafkaBridgeConsumer -->|"3. Source Record Validation<br/>against Postgres"| Postgres
    KafkaBridgeConsumer -->|"4. Publish Workflow Task<br/>(Routing Key: workflow.stage.v1)"| TaskExchange
    TaskExchange -->|"Direct Route"| TaskQueue
    TaskExchange -.->|"Publisher Confirmed ACK"| KafkaBridgeConsumer
    KafkaBridgeConsumer -.->|"5. Commit Kafka Offset<br/>(Only after Rabbit confirms)"| DomainTopic

    %% Task Consumption
    TaskQueue -->|"6. Basic.Deliver Task"| WorkflowWorker
    WorkflowWorker -->|"7. Execute Stage Handler<br/>& Update State in ACID Tx"| Postgres

    %% Worker Outcomes
    WorkflowWorker -->|"8a. Success & Next Stage<br/>Publish task to eventflow.tasks.x"| TaskExchange
    WorkflowWorker -->|"8b. Transient Error<br/>Publish to retry exchange (retry.5s/retry.30s)"| RetryExchange
    WorkflowWorker -->|"8c. Permanent Failure / Exhausted<br/>Publish to dead exchange"| DeadExchange
    WorkflowWorker -.->|"9. Basic.Ack Delivery<br/>(Only after state/retry published)"| TaskQueue

    %% Retry Delay Flow
    RetryExchange -->|"Routing Key: retry.5s"| RetryQueue5s
    RetryExchange -->|"Routing Key: retry.30s"| RetryQueue30s
    RetryQueue5s -->|"Message Expired (5s TTL)"| TaskExchange
    RetryQueue30s -->|"Message Expired (30s TTL)"| TaskExchange

    %% Dead Letter Routing
    DeadExchange -->|"Routing Key: workflow.dead_lettered"| DeadQueue
```

---

## Why Both Kafka and RabbitMQ?

A common question in distributed architecture interviews is: *Why use both Kafka and RabbitMQ in the same architecture?*

EventFlow AI pairs them deliberately based on their orthogonal strengths:

| Architectural Requirement | Apache Kafka | RabbitMQ | How EventFlow AI Uses It |
| :--- | :--- | :--- | :--- |
| **Data Model** | Distributed partitioned commit log | Smart message broker / dumb consumer | Kafka retains immutable event history; RabbitMQ distributes tasks to workers. |
| **Consumption Semantics** | Partition-ordered reading by offset | Point-to-point work queues with `Basic.Ack` | Kafka streams domain and lifecycle events; RabbitMQ load-balances individual stage tasks across workers. |
| **Retries & Delays** | Difficult (blocks partition head-of-line) | Native support via Dead-Letter Exchanges and TTL queues | Failed stages route to RabbitMQ TTL queues (`retry.5s`, `retry.30s`) without stalling unrelated workflows. |
| **Retention** | Long-term log retention & replay | Ephemeral; deleted immediately upon `ack` | Kafka enables full system event replay and analytics projection; RabbitMQ maintains lean active queues. |

---

## Detailed Pipeline Stages

### 1. Ingestion to Kafka (`apps/processing/outbox.py`)
- The outbox publisher claims batches of ready rows from PostgreSQL.
- It publishes to Kafka topic `eventflow.domain.events.v1`, partitioned by `key=event_id`.
- This ensures all events relating to the same event ID land on the same Kafka partition in strict temporal order.

### 2. Kafka-to-Rabbit Bridge (`apps/processing/pipeline.py` & `consume_domain_events.py`)
- The bridge worker (`ConfluentKafkaConsumer`) subscribes to `eventflow.domain.events.v1` in consumer group `eventflow.kafka-to-rabbit.v1`.
- For each record:
  1. It decodes the payload contract.
  2. It performs a **source verification check** against PostgreSQL to guarantee the `Event` and `Workflow` records exist and match the payload checksum.
  3. It constructs a discrete workflow task envelope:
     ```python
     task = make_workflow_task(event, workflow.id)
     ```
  4. It publishes the task to RabbitMQ exchange `eventflow.tasks.x` with routing key `workflow.stage.v1` using **publisher confirms**.
  5. **Synchronous Commit**: Crucially, `kafka_consumer.commit(record)` is executed **only after RabbitMQ confirms publication**. If RabbitMQ is down, the Kafka offset is not committed, and the message will be reprocessed when the service recovers.

### 3. Task Execution in Workflow Worker (`apps/processing/pipeline.py`)
- `PikaRabbitAdapter` consumes from `eventflow.tasks.workflow.q`.
- When a task arrives:
  1. `process_workflow_task(task)` runs the designated stage handler (e.g. order validation, inventory reservation, payment authorization).
  2. The database updates (`Workflow`, `WorkflowAttempt`, `ProcessingLog`, commerce models) are committed in a PostgreSQL transaction.
  3. Depending on the decision returned:
     - **Next Stage (`ENQUEUE_NEXT`)**: Publishes the next stage task back to `eventflow.tasks.x`.
     - **Transient Retry (`RETRY`)**: Publishes to `eventflow.retry.x` with routing key `retry.5s` or `retry.30s`.
     - **Permanent Dead-Letter (`DEAD_LETTER`)**: Publishes to `eventflow.dead.x` with routing key `workflow.dead_lettered`.
  4. `delivery.ack()` is dispatched to RabbitMQ **only after** all downstream actions and database writes succeed.

---

## At-Least-Once Delivery & Duplicate Processing

> **Important Guarantee Note**: EventFlow AI does **NOT** claim exactly-once processing. It implements **at-least-once delivery with idempotent deduplication**.

### Where duplicates can occur:
1. **Publisher Crash after Kafka Send**: If `outbox-publisher` sends an event to Kafka but crashes before marking `published_at` in PostgreSQL, the row's lease expires and another worker re-publishes it to Kafka.
2. **Bridge Crash after RabbitMQ Publish**: If `kafka-consumer` enqueues a task to RabbitMQ but crashes before committing its Kafka offset, the Kafka partition rebalances and re-delivers the record.
3. **Worker Crash after DB Commit**: If `workflow-worker` completes a stage, updates PostgreSQL, but crashes before sending `delivery.ack()` to RabbitMQ, RabbitMQ re-queues the message upon socket closure.

### How duplicates are handled safely:
- Every entity has natural or synthetic idempotency constraints:
  - Events: Unique constraint on `(client_id, source, idempotency_key)`.
  - Workflow Attempts: Unique constraint on `(workflow_id, stage, direction, attempt_number)`.
  - Inventory Reservations: Checked against existing reservation records.
  - Lifecycle Events: Deduplicated by ClickHouse `ReplacingMergeTree` on `(event_date, workflow_id, event_time, lifecycle_id)`.

---

## Implementation Status
- **Status**: Implemented and Verified in Local & Docker Compose Environments.
- **Source Paths**:
  - Broker Topology Definitions: [`apps/processing/topology.py`](file:///d:/eventflow-ai/apps/processing/topology.py)
  - Pipeline Execution Logic: [`apps/processing/pipeline.py`](file:///d:/eventflow-ai/apps/processing/pipeline.py)
  - Kafka Consumer Command: [`apps/processing/management/commands/consume_domain_events.py`](file:///d:/eventflow-ai/apps/processing/management/commands/consume_domain_events.py)
  - Workflow Worker Command: [`apps/processing/management/commands/process_workflows.py`](file:///d:/eventflow-ai/apps/processing/management/commands/process_workflows.py)
  - Kafka Adapter: [`apps/processing/adapters/kafka.py`](file:///d:/eventflow-ai/apps/processing/adapters/kafka.py)
  - RabbitMQ Adapter: [`apps/processing/adapters/rabbitmq.py`](file:///d:/eventflow-ai/apps/processing/adapters/rabbitmq.py)

