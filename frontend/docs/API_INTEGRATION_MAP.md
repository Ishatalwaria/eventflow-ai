# EventFlow AI — Frontend API Integration Map

This document specifies the HTTP API contracts, authentication mechanisms, request/response structures, and endpoint mappings between the React frontend operations console and the Django REST backend.

---

## Architecture & Authentication Overview

EventFlow AI implements a dual authentication tier:

1. **User Authentication (Web Console):**
   - **Protocol:** Django Session Authentication with encrypted `HttpOnly`, `SameSite=Lax`, `Secure` cookies.
   - **CSRF Token:** Handled transparently by Axios using standard `X-CSRFToken` headers acquired via `GET /api/v1/auth/csrf`.
   - **Session Endpoints:** `/api/v1/auth/register`, `/api/v1/auth/login`, `/api/v1/auth/logout`, `/api/v1/auth/me`, `/api/v1/auth/password-reset`.
   - **In-Console API Client Management:** Authenticated users can generate, inspect, and revoke ingestion client tokens directly via `/api/v1/clients`.

2. **API Client Authentication (Machine Ingestion):**
   - **Protocol:** HTTP Bearer header (`Authorization: Bearer <CLIENT_UUID>.<SECRET>`).
   - **Target:** Used by high-throughput microservices and event producers submitting events to `/api/v1/events` and `/api/v1/events/batch`.
   - **Console Usage:** Operators may also input an API Client token into the console Settings to inspect tenant-isolated streams or access global ClickHouse analytics when granted the `can_view_analytics` capability.

3. **General Conventions:**
   - **API Origin:** Configured in `VITE_API_BASE_URL` (defaults to `http://localhost:8000`). Vite proxies `/api` and `/health` requests during development to ensure same-origin cookie delivery.
   - **Standard Error Envelope:**
     ```json
     {
       "error": {
         "code": "STRING_ERROR_CODE",
         "message": "Human-readable description.",
         "request_id": "UUID-OR-NULL",
         "details": {}
       }
     }
     ```
   - **Correlation Headers:** Responses return `X-Request-ID` and `X-Trace-ID` for end-to-end tracing across application and worker logs.

---

## Comprehensive Endpoint Map

| Method | Endpoint | Auth Required | Frontend Feature Area | Summary & Purpose |
|---|---|---|---|---|
| **GET** | `/health/live` | None (Public) | System Health | Process liveness probe. Fast 200 OK response; does not query dependencies. |
| **GET** | `/health/ready` | None (Public) | System Health | Database readiness probe. Executes shallow PostgreSQL check. |
| **GET** | `/health/services` | Session or API Client | System Health | Comprehensive server-side probe of PostgreSQL, Kafka, RabbitMQ, ClickHouse, and worker metric availability. |
| **GET** | `/api/v1/auth/csrf` | None (Public) | Auth / Session | Initializes CSRF cookie and returns `{ csrfToken: string }`. |
| **POST** | `/api/v1/auth/register` | None (Public) | Signup Page | Registers a new user, establishes session, and auto-provisions a default workspace client. |
| **POST** | `/api/v1/auth/login` | None (Public) | Login Page | Authenticates email/password, sets HttpOnly session cookie, and returns user profile. |
| **POST** | `/api/v1/auth/logout` | Session | Navigation / Profile | Terminates session and clears active cookies. |
| **GET** | `/api/v1/auth/me` | Session or API Client | App Shell / State | Returns active user profile, permissions, and tenant context. |
| **POST** | `/api/v1/auth/password-reset` | None (Public) | Forgot Password | Requests a password reset token for the specified email. |
| **POST** | `/api/v1/auth/password-reset/confirm` | None (Public) | Reset Password | Validates reset token and sets new password. |
| **GET** | `/api/v1/clients` | Session (User) | Settings | Lists all API ingestion clients owned by the authenticated user. |
| **POST** | `/api/v1/clients` | Session (User) | Settings | Generates a new API client credential. Reveals the raw Bearer token once. |
| **POST** | `/api/v1/clients/{client_id}/revoke` | Session (User) | Settings | Immediately revokes an API client credential. |
| **POST** | `/api/v1/events` | API Client Bearer | Ingestion / Events | Ingests a single event envelope transactionally into PostgreSQL and Outbox. |
| **POST** | `/api/v1/events/batch` | API Client Bearer | Ingestion / Events | Transactionally ingests up to 50 event envelopes in an all-or-nothing batch. |
| **GET** | `/api/v1/events` | Session or API Client | Events Explorer | Paginated list of historical events with query filters (`search`, `event_type`, `date_from`, `date_to`). |
| **GET** | `/api/v1/events/{event_id}` | Session or API Client | Event Detail | Detailed event metadata, payload, and nested workflow summary. |
| **GET** | `/api/v1/workflows` | Session or API Client | Workflows Console | Paginated workflow list filtered by state (`RECEIVED`, `PROCESSING`, `SUCCEEDED`, `FAILED`, etc.). |
| **GET** | `/api/v1/workflows/{workflow_id}` | Session or API Client | Workflow Detail | Detailed workflow record, execution timeline, and attempt history. |
| **GET** | `/api/v1/incidents` | Session or API Client | AI Incidents | Paginated list of persisted AI incident root-cause investigations. |
| **GET** | `/api/v1/incidents/{incident_id}` | Session or API Client | Incident Detail | Full persisted incident summary, confirmed facts, hypotheses, and evidence snapshot. |
| **POST** | `/api/v1/workflows/{workflow_id}/incident-summary` | Session or API Client | Workflow Detail / Incidents | Generates an evidence-grounded AI incident analysis for a `FAILED` or `DEAD_LETTERED` workflow. |
| **GET** | `/api/v1/analytics/overview` | Session or API Client | Overview Dashboard | Aggregate summary: 7-day terminal volume, event/workflow counts, latency, and outbox state. |
| **GET** | `/api/v1/analytics/tenant-lifecycle` | Session or API Client | Analytics | Tenant-scoped PostgreSQL current-state lifecycle percentiles, retries, and success rates. |
| **GET** | `/api/v1/analytics/lifecycle` | Capability: `can_view_analytics` | Analytics | High-volume system-wide lifecycle analytics from ClickHouse `ReplacingMergeTree`. |
| **GET** | `/api/schema/` | None (Public) | Developer / API | Raw OpenAPI 3.0.3 specification generated by drf-spectacular. |
| **GET** | `/api/docs/` | None (Public) | Developer / API | Interactive Swagger UI documentation. |
| **GET** | `/metrics` | `X-Metrics-Token` | Operations Scraper | Prometheus exposition format (internal/server-side scraping only). |

---

## Ingestion Event Contract (`order.created` v1)

```json
{
  "event_type": "order.created",
  "schema_version": 1,
  "source": "checkout-service",
  "idempotency_key": "checkout-tx-994821",
  "occurred_at": "2026-11-02T10:00:00Z",
  "correlation_id": "corr-tx-994821",
  "payload": {
    "order_id": "ORD-2026-11-001",
    "currency": "USD",
    "total_minor_units": 15000,
    "items": [
      {
        "sku": "ITEM-LAPTOP-PRO",
        "quantity": 1
      }
    ]
  }
}
```

### Response Schema (`201 Created` or `200 OK` on Idempotent Replay)
```json
{
  "event_id": "7b5ce162-d27a-4934-8c76-26732cf31eb4",
  "workflow_id": "c3e8006e-8212-4217-bd01-c88e7b953d68",
  "workflow_state": "RECEIVED",
  "duplicate": false
}
```

---

## Incident Analysis Contract

Persisted incident investigations structure findings with strict evidence citations:

```json
{
  "id": "e4a2c5a1-7711-4fa2-bf5a-4e4ad70c6489",
  "workflow_id": "c3e8006e-8212-4217-bd01-c88e7b953d68",
  "evidence_hash": "a1b2c3d4...",
  "summary": {
    "headline": "Workflow failed due to repeated worker timeouts during order validation.",
    "confirmed_facts": [
      {
        "statement": "Workflow reached DEAD_LETTERED state at order_validation stage.",
        "evidence_ids": ["workflow:c3e8006e"]
      },
      {
        "statement": "Attempts 1 and 2 terminated with WORKER_TIMEOUT.",
        "evidence_ids": ["attempt:c3e8006e-a1", "attempt:c3e8006e-a2"]
      }
    ],
    "hypotheses": [
      {
        "statement": "Downstream inventory service saturation likely exceeded the 5-second socket timeout.",
        "evidence_ids": ["attempt:c3e8006e-a1", "attempt:c3e8006e-a2"],
        "confidence": 0.8
      }
    ],
    "unknowns": [
      "Downstream inventory service internal error logs are unavailable in the evidence context."
    ],
    "recommended_checks": [
      "Review inventory API latency metrics between cited attempt intervals."
    ],
    "insufficient_evidence": false
  },
  "provider": "gemini",
  "model": "gemini-3.5-flash-lite",
  "latency_ms": 1120,
  "created_at": "2026-11-02T10:05:00Z"
}
```
