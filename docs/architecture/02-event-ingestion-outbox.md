# Diagram 2: Event Ingestion and Transactional Outbox

## Purpose
This document details the exact sequence and failure mechanics of the **Event Ingestion and Transactional Outbox** pattern implemented in EventFlow AI. It illustrates how the platform achieves atomic database persistence and asynchronous event publication without dual-write hazards.

---

## Ingestion & Outbox Sequence Diagram

```mermaid
sequenceDiagram
    autonumber
    actor Client as External Client / Producer
    participant API as Django REST API (apps/events/views.py)
    participant Auth as Auth & Scope (apps/common/authentication.py)
    participant Service as Ingestion Service (apps/events/services.py)
    participant DB as PostgreSQL (ACID Transaction)
    participant OutboxWorker as Outbox Publisher (publish_outbox.py)
    participant Kafka as Apache Kafka (eventflow.domain.events.v1)

    %% Step 1: Ingress & Validation
    Client->>API: POST /api/v1/events (Bearer Token + Event Batch)
    activate API
    API->>Auth: Authenticate Bearer <client_uuid>.<secret>
    activate Auth
    Auth-->>API: APIClient Authenticated (Owner Scope Bound)
    deactivate Auth

    API->>API: Validate JSON Contract (EventBatchSerializer)
    alt Contract Invalid (400 Bad Request)
        API-->>Client: HTTP 400 Bad Request (Validation Errors)
    end

    %% Step 2: Atomic Persistence with Savepoint Idempotency
    API->>Service: accept_events(client, envelopes, request_id)
    activate Service
    Service->>DB: BEGIN Transaction (atomic batch)

    loop For each event envelope in batch
        Service->>DB: SAVEPOINT before_insert
        Service->>DB: INSERT INTO events (id, client_id, event_type, idempotency_key, payload, ...)
        
        alt Unique Constraint Violation on (client_id, source, idempotency_key)
            DB-->>Service: IntegrityError (Duplicate detected)
            Service->>DB: ROLLBACK TO SAVEPOINT before_insert
            Service->>DB: SELECT * FROM events WHERE client=client AND idempotency_key=key
            DB-->>Service: Return Existing Event & Workflow
            Note over Service: Mark AcceptedEvent(duplicate=True)
        else Fresh Event Insert
            DB-->>Service: Event Created (UUID assigned)
            Service->>DB: INSERT INTO workflows (event_id, workflow_type, state='RECEIVED', current_stage='accepted')
            DB-->>Service: Workflow Created
            Service->>DB: INSERT INTO processing_logs (event_id, workflow_id, message='Event accepted')
            Service->>DB: INSERT INTO outbox_messages (topic='eventflow.domain.events.v1', dedupe_key=..., payload=...)
            Note over Service,DB: Written inside same atomic transaction
        end
    end

    Service->>DB: COMMIT Transaction
    deactivate Service
    API-->>Client: HTTP 200 OK / 202 Accepted ([{event_id, workflow_id, status='accepted', duplicate: bool}])
    deactivate API

    %% Step 3: Asynchronous Outbox Publishing Loop
    Note over OutboxWorker,Kafka: Asynchronous Background Loop (Independent of HTTP Request)
    loop Every Poll Interval (0.5s - 2.0s)
        OutboxWorker->>DB: BEGIN Transaction
        OutboxWorker->>DB: SELECT * FROM outbox_messages<br/>WHERE published_at IS NULL AND dead_lettered_at IS NULL AND available_at <= NOW()<br/>ORDER BY created_at, id LIMIT 25<br/>FOR UPDATE SKIP LOCKED
        DB-->>OutboxWorker: Return Claimed Rows
        OutboxWorker->>DB: UPDATE outbox_messages SET lease_owner=UUID, lease_expires_at=NOW()+60s
        OutboxWorker->>DB: COMMIT Transaction (Lease Secured)

        loop For each claimed message
            OutboxWorker->>Kafka: publish(topic=DOMAIN_TOPIC, key=event_id, value=encoded_json)
            
            alt Kafka Broker Confirms Receipt
                Kafka-->>OutboxWorker: ACK (Offset Assigned)
                OutboxWorker->>DB: UPDATE outbox_messages<br/>SET published_at=NOW(), publish_attempts += 1,<br/>lease_owner=NULL, lease_expires_at=NULL<br/>WHERE id=message_id AND lease_owner=UUID
            else Kafka Broker Unavailable / Timeout
                Kafka--xOutboxWorker: BrokerUnavailable / Timeout
                alt attempts < OUTBOX_MAX_ATTEMPTS (12)
                    OutboxWorker->>DB: UPDATE outbox_messages<br/>SET publish_attempts += 1,<br/>available_at = NOW() + (2^attempts * base_delay),<br/>lease_owner=NULL, lease_expires_at=NULL,<br/>last_error_code='KAFKA_UNAVAILABLE'
                else attempts >= 12 (Exhausted)
                    OutboxWorker->>DB: UPDATE outbox_messages<br/>SET dead_lettered_at=NOW(),<br/>lease_owner=NULL, lease_expires_at=NULL,<br/>last_error_code='KAFKA_UNAVAILABLE'
                end
            end
        end
    end
```

---

## Detailed Component Responsibilities

### 1. Ingestion Endpoint (`apps/events/views.py` & `apps/events/services.py`)
- Receives HTTP payload matching `EventBatchSerializer` (`event_type`, `schema_version`, `source`, `idempotency_key`, `occurred_at`, `correlation_id`, `payload`).
- Generates a unique `request_id` for end-to-end distributed tracing.
- Executes `accept_events()` inside a PostgreSQL transaction (`@transaction.atomic`).

### 2. Savepoint Idempotency Mechanism
- To handle concurrent duplicate requests safely, `apps/events/services.py` wraps each item insert in a sub-transaction savepoint:
  ```python
  with transaction.atomic():
      event = Event.objects.create(...)
      workflow = Workflow.objects.create(...)
      record_initial_domain_outbox(event, workflow_id=workflow.id)
      ProcessingLog.objects.create(...)
  ```
- If an `IntegrityError` is triggered by PostgreSQL's `event_client_source_idem_uniq` constraint (`UniqueConstraint(fields=["client", "source", "idempotency_key"])`), only the savepoint rolls back. The transaction queries the previously created event and returns `AcceptedEvent(duplicate=True)` without failing the entire batch.

### 3. Outbox Row Invariant (`apps/processing/models.py`)
- The `OutboxMessage` record is written to PostgreSQL **in the exact same ACID transaction** as the `Event` and `Workflow`.
- Fields include:
  - `dedupe_key`: e.g. `event:<uuid>:domain.v1`
  - `topic`: `eventflow.domain.events.v1`
  - `payload`: Normalized JSON contract
  - `available_at`: Earliest timestamp when this message can be claimed
  - `lease_owner` & `lease_expires_at`: Worker claim lock
  - `published_at` & `dead_lettered_at`: Terminal outbox states

### 4. Competing Consumer Worker Leasing (`apps/processing/outbox.py`)
- To allow multiple `outbox-publisher` instances to run concurrently without publishing duplicate messages or encountering race conditions, rows are claimed using PostgreSQL's `SKIP LOCKED`:
  ```python
  OutboxMessage.objects.select_for_update(skip_locked=True).filter(
      published_at__isnull=True,
      dead_lettered_at__isnull=True,
      available_at__lte=now,
      lease_expires_at__isnull=True | lease_expires_at__lte=now
  ).order_by("created_at", "id")[:batch_size]
  ```
- Claimed rows receive a 60-second lease (`OUTBOX_LEASE_SECONDS = 60`). If a publisher container crashes mid-publish, the lease expires and another instance reclaims the row.

---

## Why the Transactional Outbox Eliminates the Dual-Write Problem

### The Dual-Write Hazard (Direct Broker Publishing)
In naive architectures, the API controller inserts records into the database and immediately calls `kafka_producer.send()`:
1. If the database commit succeeds but Kafka is unreachable, the event is permanently lost to downstream consumers.
2. If Kafka publish succeeds but the database transaction fails to commit (e.g. database disconnect), Kafka processes a "phantom event" that does not exist in the database.

### The EventFlow AI Guarantee
- By writing the outbox row **inside PostgreSQL's transaction**, either **both** the event state and the outbox record commit, or **neither** does.
- External publication is handled asynchronously by `outbox-publisher`.
- Even if Kafka is down for minutes or hours, outbox rows queue safely in PostgreSQL. Once Kafka recovers, the publisher resumes seamlessly.

---

## Reliability & Delivery Guarantees

| Guarantee | Level | Mechanism |
| :--- | :--- | :--- |
| **Ingestion Atomicity** | **Strict ACID** | All 4 entities (`Event`, `Workflow`, `Log`, `Outbox`) commit atomically in PostgreSQL. |
| **Ingestion Idempotency** | **Deduplicated** | `(client, source, idempotency_key)` database unique constraint returns existing records on replay. |
| **Publishing Delivery** | **At-Least-Once** | Messages are committed as published only after Kafka acknowledges receipt. Crash between publish and update results in safe replay downstream. |
| **Exponential Backoff** | **Bounded Retries** | Failures back off with $2^{\text{attempts}} \times \text{base\_delay}$, capped at 12 attempts before dead-lettering. |

---

## Implementation Status
- **Status**: Implemented and Verified.
- **Source Paths**:
  - Ingestion Logic: [`apps/events/services.py`](file:///d:/eventflow-ai/apps/events/services.py)
  - Models: [`apps/events/models.py`](file:///d:/eventflow-ai/apps/events/models.py), [`apps/processing/models.py`](file:///d:/eventflow-ai/apps/processing/models.py)
  - Outbox Management: [`apps/processing/outbox.py`](file:///d:/eventflow-ai/apps/processing/outbox.py)
  - Publisher Command: [`apps/processing/management/commands/publish_outbox.py`](file:///d:/eventflow-ai/apps/processing/management/commands/publish_outbox.py)

