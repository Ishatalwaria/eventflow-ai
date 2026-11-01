# 02 — Backend requirement gap analysis

Status meanings: implemented and verified means supported by tests/checks or live evidence at the stated scope. Implemented, unverified means code exists but the real integration was not exercised. Partial means a requirement or end-user capability is incomplete. Blocked means environment prevented verification. Passing unit tests do not prove distributed operation.

## M0 — Foundation

| Requirement | Status | Evidence and assessment |
|---|---|---|
| Settings separation/environment variables | Implemented and Django-check verified | config/settings/base.py, local.py, production.py, test.py, postgres_integration.py; env-backed configuration and production validation. |
| PostgreSQL and migrations | Partial verification | DB container healthy. makemigrations --check --dry-run reported no model changes but warned it could not verify migration history due local socket permission. Readiness API did query DB successfully. |
| Structured logging | Implemented and unit-tested | config/logging.py redacts selected credential/PII patterns and emits request context. Pattern-based redaction cannot recognize arbitrary secrets. |
| DRF defaults | Implemented with explicit protected views | Views use client auth and IsAuthenticated; global defaults still include Session/Basic and AllowAny, so a future view must opt into restrictive settings. |
| OpenAPI | Implemented and live-verified | OpenAPI 3.0.3 returned expected routes and ClientBearer scheme; Swagger configured. |
| Health/readiness | Implemented and live-verified | /health/live returned status ok; /health/ready returned ready/database ok. Liveness ignores dependencies; readiness only checks PostgreSQL. |
| Docker/developer setup | Implemented, partially verified | Compose config passed. API and DB healthy; Kafka/RabbitMQ/ClickHouse exited. README/runbook provide setup. |
| pytest/Ruff | Implemented and verified | 88 tests passed, 4 skipped; Ruff lint and formatting passed. |

## M1 — Event ingestion and workflow API

| Requirement | Status | Evidence and assessment |
|---|---|---|
| Client auth, hashed secret, revocation/rotation | Implemented and live-tested | APIClientAuthentication, common.services and client_credentials command. Temporary clients verified authorized and denied endpoint behavior and were revoked. |
| Event validation and request bounds | Implemented and tested | apps/events/contracts.py and BoundedJSONParser; 256 KiB and batch 1–50. |
| Single and batch create | Implemented and live-tested for single event | Views delegate to atomic accept_events service; live single event acceptance, retrieval and workflow processing verified. Batch remains covered by automated tests. |
| Idempotency and atomic records | Implemented and tested | DB constraint plus savepoint/duplicate lookup in apps/events/services.py; rollback/atomicity tests. Concurrent race is PostgreSQL-only and skipped locally; CI defines a separate PG job. Reusing a key with changed body returns old record; desired semantics are ambiguous. |
| Event/workflow retrieval and filtering | Implemented for event list/detail and workflow list/detail | Event list supports tenant scope, page/search/type/date filters; event and workflow details and workflow state/page filters remain. Live authenticated event collection and vertical slice verified 2026-10-30. |
| Consistent errors and request IDs | Implemented and tested | Common exception handler and middleware return IDs and safe envelope. |

## M2 — Reliable event processing

| Requirement | Status | Evidence and assessment |
|---|---|---|
| Kafka adapters, topics, groups, versioned contracts | Implemented and live-verified | Required topics were inspected; broker round trips and Kafka unavailable/restore behavior passed in local drills. |
| Transactional outbox and concurrent claim | Implemented and live-verified for retry/drain | claim_outbox_messages uses select_for_update(skip_locked=True), leases rows, then publishes outside transaction; Kafka outage left an unpublished row that drained after restore. |
| Kafka-to-Rabbit forwarding and offset semantics | Implemented and live-verified for Rabbit unavailable recovery | Kafka commit follows Rabbit publish; Rabbit outage retained work until recovery and workflow reached terminal state. |
| Durable Rabbit topology, manual ack/prefetch, retries/DLQ | Implemented and live-verified for durable queue/redelivery | Durable topology, TTL routes, prefetch 1; queued and in-flight unacknowledged work recovered after worker restart. |
| Worker stage/state/attempt/lifecycle | Implemented and unit-tested | Workflow service records attempt/state and lifecycle outbox transactionally. Only order_validation is a recorded stage; inventory check is simulated within it. |
| Duplicate/redelivery/crash window | Unit-tested, live unverified | Database idempotency and crash-after-commit case are tested; no RabbitMQ at audit. |
| Graceful shutdown/recovery | Implemented and partially verified | Management commands register SIGINT/SIGTERM and retry connections. Worker SIGKILL requeue was verified; worker Compose healthchecks remain disabled, so Up alone is not readiness. |
| Required failure scenarios | Verified for this local Compose run | Kafka, RabbitMQ, worker interruption/redelivery, ClickHouse outage/replay and LLM provider safe failure were exercised; see operations-runbook evidence. |

## M3 — ClickHouse analytics

| Requirement | Status | Evidence and assessment |
|---|---|---|
| Schema and ordering key | Implemented | DDL defines lifecycle facts, monthly partitions, ReplacingMergeTree and workflow/date ordering. |
| Sink and replay duplicate strategy | Implemented; live blocked | Deterministic UUID and FINAL query; consumer commits Kafka only after insert confirmation. Unit tests cover fake outage/commit order. |
| Required queries | Implemented in backend query function and bounded HTTP API | Per-minute terminal lifecycle counts, success/failure rates, p50/p95/p99, retry distribution, frequent error codes, stage failure rate and freshness in apps/analytics/queries.py and `/api/v1/analytics/lifecycle`. Access requires explicit `can_view_analytics` capability because aggregates are system-wide. |
| Retry/recovery | Durable Kafka replay implemented | Offset left uncommitted on sink failure; consumer reconnects with bounded backoff interval. ClickHouse is eventually consistent. |
| Seeded live query/duplicate test | Verified 2026-10-31 | Opt-in ClickHouse suite passed; API returned seeded success/failure values and eventual-consistency metadata; regular client was denied. |

## M4 — AI Incident Assistant

| Requirement | Status | Evidence and assessment |
|---|---|---|
| Evidence IDs, bounds, redaction | Implemented and tested | 24-hour window, capped attempts/logs/items/text; excludes payload and arbitrary log attributes; canonical evidence hash. Health metrics explicitly unavailable. |
| Provider abstraction/mock/live adapters | Implemented; live provider unverified | Mock, OpenAI and Gemini adapters; tests fake network/errors. No live provider request made. |
| Structured output/citation validation | Implemented and tested | Strict schema and supplied evidence-ID validation; insufficient-evidence rules and labeled fixtures. |
| Prompt injection/no tools or workflow mutation | Implemented and tested | Evidence treated as data; adapters configure no tools; summary creation does not mutate workflow state. |
| Timeouts/retries/rate limit/metadata | Implemented and API-tested | Bounded timeout/retries, DB-backed client throttle, provider/model/tokens/latency stored. |
| Incident persistence/retrieval | Implemented and live-verified with local provider | Summary persisted and tenant-scoped read/list APIs return history; search/state filters, pagination and cross-tenant isolation verified 2026-10-31. External provider calls remain unverified. |

## M5 — Production-style quality

| Requirement | Status | Evidence and assessment |
|---|---|---|
| Structured logs and propagated IDs | Implemented and tested | JSON logs and request/event/workflow/correlation IDs propagate. X-Trace-ID duplicates request ID; no span export. |
| Metrics | Implemented; scraping unverified | Prometheus API/worker metrics require token. Not scraped in audit; dependencies down affect metrics. |
| Timeouts, bounds, pagination, safe errors | Implemented and tested | DB/provider/broker limits, payload and response bounds, page bounds and safe error handler exist. |
| Least privilege and TLS settings | Configured, deployment unverified | Production settings enforce non-local TLS services and strong secrets; actual deployed grants/TLS unavailable. |
| CI, dependency/image checks | Configured; result not observed | CI defines Ruff, checks/tests, PostgreSQL/broker/ClickHouse, pip-audit and Trivy. No run result retrieved; frontend omitted. |
| Non-root container | Implemented for API image | Dockerfile uses UID/GID 10001. |
| Five failure drills | Verified for local Compose run | See `docs/operations-runbook.md` dated 2026-10-31; provider failure was verified using the targeted API test without external credentials. |

## M6 — Kubernetes/performance validation

Not implemented or run, as requested. The supplied backend instruction document references Kubernetes later but does not define detailed M6 acceptance criteria; establish them before planning.
