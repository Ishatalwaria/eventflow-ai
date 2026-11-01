# 01 — Architecture audit

## Sources reviewed

Reviewed repository source, the supplied backend permanent instructions and frontend development instructions, phase prompts in this conversation, and live OpenAPI. Backend instructions detail M0–M5, not M6. No source code was changed during this audit.

## Architecture

    React + Vite frontend
      -> Django REST API
      -> PostgreSQL (transactional source of truth)
      -> transactional outbox -> Kafka domain topic
      -> Kafka consumer -> RabbitMQ durable task/retry/DLQ queues
      -> workflow worker -> PostgreSQL attempt/state/lifecycle outbox
      -> Kafka lifecycle topic -> analytics consumer -> ClickHouse projection

    Incident endpoint -> bounded evidence builder -> mock/OpenAI/Gemini adapter
      -> strict structured response validation -> PostgreSQL IncidentSummary

The implementation is distributed across apps/events, apps/processing, apps/workflows, apps/analytics and apps/incidents. PostgreSQL remains authoritative; broker delivery is at least once; ClickHouse is an eventually consistent projection.

## Repository map

| Layer | Main implementation |
|---|---|
| Django config/startup | config/settings/{base,local,production,test,postgres_integration}.py; config/{asgi,wsgi,urls}.py; config/gunicorn.conf.py |
| Domain apps | apps/common, events, workflows, processing, incidents, analytics |
| Persistence | Django models/migrations per app. Event uniqueness is client + source + idempotency key; attempt and outbox dedupe keys are constrained. |
| HTTP/OpenAPI | DRF views/serializers and drf-spectacular; live schema is OpenAPI 3.0.3. |
| Auth | apps/common/authentication.py; password-hashed client credentials, revocation and management-command create/rotate/revoke. |
| Processing | Project-owned ports, Kafka/Rabbit adapters, management commands, outbox and workflow service. |
| Analytics | ClickHouse DDL/sink/query function, lifecycle report, bounded read-only DRF endpoint, and explicitly granted system-wide analytics capability. |
| Incident assistant | Bounded evidence builder, mock/OpenAI/Gemini adapters, response validation and persisted IncidentSummary. |
| Observability | JSON formatter, request context, Prometheus API/worker metrics and health views. X-Trace-ID equals request ID; it is not a distributed span. |
| Delivery/operations | Docker Compose, non-root API Dockerfile, GitHub Actions, security checklist and recovery runbook. |
| Frontend | Separate frontend app with routes, shared components, API client/types/hooks, feature pages and Vitest tests. |

## Live API contract

GET /api/schema/?format=json returned OpenAPI 3.0.3 with the ClientBearer scheme and these paths:

| Method | Path | Auth |
|---|---|---|
| GET | /health/live | None |
| GET | /health/ready | None |
| POST | /api/v1/events | Client bearer |
| POST | /api/v1/events/batch | Client bearer |
| GET | /api/v1/events/{event_id} | Client bearer, tenant-scoped |
| GET | /api/v1/workflows | Client bearer, tenant-scoped; state/page/page_size |
| GET | /api/v1/workflows/{workflow_id} | Client bearer, tenant-scoped |
| POST | /api/v1/workflows/{workflow_id}/incident-summary | Client bearer, tenant-scoped, throttled |
| GET | /api/schema/, /api/docs/ | None |

/metrics is excluded from the schema and requires X-Metrics-Token. / redirects to Swagger; /admin/ is Django admin. Event collection, incident list/detail and lifecycle analytics APIs were added and verified 2026-10-30/31. Per-service health APIs remain unavailable.

Operation-level inspection found schema drift: GET /api/v1/workflows documents page and page_size but omits the state query parameter implemented by WorkflowListQuerySerializer/list(). API operations document successful responses but not common 400/401/403/404/413/429/500 error envelopes. The frontend API map describes state filtering and errors from implementation, but these details are not discoverable from OpenAPI.

## Architecture/contract gaps

1. Phase 4 asks for an event listing API, but backend exposes only create, batch and detail. UI lists the session’s known submission IDs via detail calls.
2. Phase 6 incident listing/history is now backed by tenant-scoped persisted list/detail endpoints.
3. Phase 7 analytics is now available through a read-only ClickHouse API protected by an explicit capability; service-specific health and Prometheus metrics remain unavailable to the frontend.
4. Settings accepts a machine/client bearer token, not a user session. A browser-visible token is appropriate only for controlled development/demo use.
5. Detailed M6 acceptance requirements were not supplied; Kubernetes is deferred.

## Assessment

The service boundaries and transactional outbox are coherent for an MVP. Main follow-up is API/product contract coverage rather than a rewrite. At audit time Kafka, RabbitMQ and ClickHouse were exited; the running consumer/worker logs showed retries. This runtime does not verify the intended whole-stack topology.
