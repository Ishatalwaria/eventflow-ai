# Diagram 10: End-to-End Event Lifecycle Sequence

## Purpose
This document presents the complete end-to-end sequence of an event traversing the entire EventFlow AI platform. It tracks an event from initial HTTP ingestion through the transactional outbox, dual-broker pipeline, saga execution, analytics projection, failure compensation, and frontend operational visualization.

---

## 1. Happy Path: Successful Event Ingestion to Saga Completion

The sequence below traces an `order.created` event executing the 6 stages of `order_fulfillment` (`validate_order` ➔ `reserve_inventory` ➔ `authorize_payment` ➔ `confirm_order` ➔ `prepare_shipment` ➔ `notify`).

```mermaid
sequenceDiagram
    autonumber
    actor Client as External Client / Producer
    participant API as Django API (apps/events)
    participant PG as PostgreSQL 16 (OLTP)
    participant OutboxPub as Outbox Publisher
    participant Kafka as Apache Kafka
    participant Bridge as Kafka-to-Rabbit Bridge
    participant Rabbit as RabbitMQ (tasks.x / workflow.q)
    participant Worker as Workflow Saga Worker
    participant CH as ClickHouse 25.12 (OLAP)
    participant AnalyticsWorker as Analytics Consumer
    actor Operator as Operator (React SPA)

    %% Phase 1: Ingestion
    Note over Client,PG: Phase 1: Ingestion & Transactional Outbox
    Client->>API: POST /api/v1/events (event_type: order.created, idempotency_key: ID-100)
    API->>PG: BEGIN Transaction
    API->>PG: INSERT Event + Workflow (state='RECEIVED')
    API->>PG: INSERT OutboxMessage (topic='eventflow.domain.events.v1')
    API->>PG: INSERT ProcessingLog (level='INFO', message='Event accepted')
    API->>PG: COMMIT Transaction
    API-->>Client: HTTP 202 Accepted {workflow_id: W-1, status: 'accepted'}

    %% Phase 2: Outbox Relay to Kafka
    Note over PG,Kafka: Phase 2: Asynchronous Outbox Relay
    OutboxPub->>PG: SELECT ... FOR UPDATE SKIP LOCKED
    OutboxPub->>Kafka: Publish eventflow.domain.events.v1 (key=event_id)
    Kafka-->>OutboxPub: ACK (Partition 0, Offset 1024)
    OutboxPub->>PG: UPDATE outbox_messages SET published_at=NOW()

    %% Phase 3: Bridge to RabbitMQ
    Note over Kafka,Rabbit: Phase 3: Kafka-to-RabbitMQ Bridge
    Kafka->>Bridge: Poll event record
    Bridge->>PG: Verify Event/Workflow source match
    Bridge->>Rabbit: Publish Task to eventflow.tasks.x (key: workflow.stage.v1)
    Rabbit-->>Bridge: Publisher Confirmed
    Bridge->>Kafka: Commit Offset (Partition 0, Offset 1024)

    %% Phase 4: Saga Forward Execution Loop
    Note over Rabbit,Worker: Phase 4: Stage-by-Stage Saga Execution
    Rabbit->>Worker: Deliver Task (stage: validate_order)
    Worker->>PG: Execute validate_order -> Update Workflow (current_stage='validate_order')
    Worker->>Rabbit: Publish Task (stage: reserve_inventory)
    Worker->>Rabbit: Basic.Ack validate_order

    Rabbit->>Worker: Deliver Task (stage: reserve_inventory)
    Worker->>PG: Execute reserve_inventory -> Decrement available, increment reserved stock
    Worker->>PG: Record Outbox Lifecycle Fact (stage='reserve_inventory', status='SUCCEEDED')
    Worker->>Rabbit: Publish Task (stage: authorize_payment)
    Worker->>Rabbit: Basic.Ack reserve_inventory

    Note over Worker,PG: Subsequent stages (authorize_payment -> confirm_order -> prepare_shipment -> notify) execute in identical sequence...

    Rabbit->>Worker: Deliver Task (stage: notify)
    Worker->>PG: Execute notify -> Update Workflow (state='SUCCEEDED', finished_at=NOW())
    Worker->>PG: Update Commerce Order (status='COMPLETED')
    Worker->>PG: Record Outbox Lifecycle Fact (stage='notify', status='SUCCEEDED')
    Worker->>Rabbit: Basic.Ack notify

    %% Phase 5: Analytics Projection
    Note over PG,CH: Phase 5: Analytical Projection to ClickHouse
    OutboxPub->>PG: Lease lifecycle outbox rows
    OutboxPub->>Kafka: Publish eventflow.workflow.lifecycle.v1 (key=workflow_id)
    Kafka->>AnalyticsWorker: Consume lifecycle events
    AnalyticsWorker->>CH: Batch INSERT INTO workflow_lifecycle_facts
    AnalyticsWorker->>Kafka: Commit Offset

    %% Phase 6: UI Dashboard Refresh
    Note over Operator,API: Phase 6: Operational Visibility
    Operator->>API: GET /api/v1/workflows/W-1
    API->>PG: Query Workflow, Attempts & Orders
    API-->>Operator: JSON {state: 'SUCCEEDED', current_stage: 'notify', order_status: 'COMPLETED'}
    Operator->>API: GET /api/v1/analytics/lifecycle
    API->>CH: Query latency quantiles & throughput
    API-->>Operator: JSON {p50: 120ms, p95: 340ms, success_rate: 1.0}
```

---

## 2. Failure Path: Payment Failure, Backward Compensation & AI Explanation

The sequence below illustrates what happens when `authorize_payment` permanently fails (e.g. `PAYMENT_DECLINED`). The saga engine rolls back previously reserved inventory (`release_inventory`), marks the workflow `FAILED`, routes to the dead-letter queue, and generates an AI incident root-cause analysis.

```mermaid
sequenceDiagram
    autonumber
    actor Client as External Client
    participant Rabbit as RabbitMQ (tasks.x / retry.x / dead.x)
    participant Worker as Workflow Saga Worker
    participant PG as PostgreSQL 16
    participant AIAPI as AI Incident API
    participant LLM as Google Gemini / OpenAI
    actor Operator as Operator (Frontend Dashboard)

    %% Failure during execution
    Note over Rabbit,Worker: Failure during Stage: authorize_payment
    Rabbit->>Worker: Deliver Task (stage: authorize_payment, attempt: 1)
    Worker->>Worker: Invoke authorize_payment handler
    Note over Worker: Payment Gateway returns: CARD_DECLINED (Permanent Failure)

    %% Saga Backward Compensation
    Note over Worker,PG: Saga Compensation Calculation
    Worker->>Worker: Inspect completed reversible stages: [reserve_inventory]
    Worker->>Worker: Compensation chain generated: [release_inventory]
    Worker->>PG: Transition Workflow -> COMPENSATING (current_stage='release_inventory')
    Worker->>PG: Record WorkflowAttempt (stage='authorize_payment', outcome='FAILED', error_code='PAYMENT_DECLINED')
    Worker->>Rabbit: Enqueue Compensation Task (direction='compensate', stage='release_inventory')
    Worker->>Rabbit: Basic.Ack authorize_payment

    %% Executing Compensation
    Rabbit->>Worker: Deliver Task (direction: compensate, stage: release_inventory)
    Worker->>PG: Execute release_inventory -> Decrement reserved stock, restore available
    Worker->>PG: Transition Workflow -> FAILED (finished_at=NOW(), last_error_code='PAYMENT_DECLINED')
    Worker->>PG: Update Commerce Order -> CANCELLED
    Worker->>Rabbit: Publish to eventflow.dead.x (Routing: workflow.dead_lettered)
    Worker->>Rabbit: Basic.Ack release_inventory

    %% Operator Inspection & AI Root Cause
    Note over Operator,LLM: Operator Incident Investigation & AI Root Cause
    Operator->>AIAPI: POST /api/v1/incidents/summary {workflow_id: W-1}
    AIAPI->>PG: Query Workflow, Event, Attempts & ProcessingLogs
    AIAPI->>AIAPI: Sanitize PII / Secrets & Generate Evidence Hash
    AIAPI->>LLM: Prompt (Grounded Evidence JSON)
    LLM-->>AIAPI: JSON {likely_root_cause: 'Card authorization failed due to issuer decline', suggested_action: 'Contact customer for alternate payment'}
    AIAPI->>PG: INSERT INTO incident_summaries
    AIAPI-->>Operator: Display AI Root Cause & Remediation Card
```

---

## Lifecycle Guarantee Highlights

1. **Transactional Ingress**: The event acceptance is committed in PostgreSQL before any broker interaction takes place.
2. **Durable Asynchronous Bridge**: Kafka offsets are only committed when RabbitMQ confirms that the task message is safely persisted on disk.
3. **Compensating Consistency**: In distributed transactions without two-phase commit (2PC), EventFlow AI relies on **Saga compensation** to ensure that failed payments do not leave stranded inventory reservations.
4. **Isolated Analytics & AI**: Neither analytical queries against ClickHouse nor AI investigations against LLM providers take read locks on active PostgreSQL saga rows, keeping the transactional core completely unaffected by reporting or incident analysis workloads.

---

## Implementation Status
- **Status**: Implemented and Verified.
- **Source Paths**:
  - Ingestion: [`apps/events/services.py`](file:///d:/eventflow-ai/apps/events/services.py)
  - Bridge: [`apps/processing/pipeline.py`](file:///d:/eventflow-ai/apps/processing/pipeline.py)
  - Saga Engine: [`apps/processing/saga/engine.py`](file:///d:/eventflow-ai/apps/processing/saga/engine.py)
  - Incident Engine: [`apps/incidents/service.py`](file:///d:/eventflow-ai/apps/incidents/service.py)
  - Analytics Sink: [`apps/analytics/sink.py`](file:///d:/eventflow-ai/apps/analytics/sink.py)

