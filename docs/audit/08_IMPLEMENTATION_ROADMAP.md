# 08 — Implementation roadmap

This roadmap now includes the evidence-based implementation performed after the audit. Kubernetes and M6 remain deferred.

## 1. Critical backend and runtime corrections

| Task | Priority | Affected files/approach | Dependencies | Acceptance and verification |
|---|---|---|---|---|
| R-01 Restore local services | P1 | Diagnose Kafka/RabbitMQ/ClickHouse container exits before changing configuration. | Docker Desktop/resources | **Partially verified 2026-10-30:** services healthy; expected topics and queues present; live broker and ClickHouse tests pass (6 passed). All three had exit 255 at the same timestamp, with no OOM or Docker error; original coordinated-stop trigger remains unknown. No configuration changes. |
| R-02 Execute authenticated event slice | P1 | Use disposable client/event; trace event, workflow, outbox, broker and response. | R-01 and valid local test token | **Verified 2026-10-30:** temporary client created/revoked; readiness 200, POST 201, event GET 200, workflow GET `SUCCEEDED`, replay 200 with `duplicate=true`, and exactly one workflow row. Event `b444fddb-300b-496f-aecc-d5173f46f05a`; workflow `3bf575d7-2eb1-493f-925a-64e9a5d6c532`. |
| R-03 Execute failure drills | P1 | Follow docs/operations-runbook.md; capture before/after outbox, queue, state and projection. | R-01, disposable data | **Verified 2026-10-31:** Kafka stop left event accepted/unpublished, restore drained it to `SUCCEEDED`; RabbitMQ stop left event `RECEIVED` with no attempts, restore reached `SUCCEEDED`; stopped worker accumulated one durable task, restart reached `SUCCEEDED`; worker was SIGKILLed with one unacked delivery while blocked on a test row lock, restart redelivered and reached `SUCCEEDED`; ClickHouse outage left workflow successful and replayed two lifecycle rows after restore. Provider transient failure API test: 1 passed, safe 503/no partial summary/workflow unchanged. Full stack healthy and outbox empty after drills. |
| R-04 PostgreSQL uniqueness race | P2 | Run PG-specific concurrent duplicate test with isolated test role/database. | Dedicated local test DB role | Race creates one event/workflow and expected duplicate response; never use production/app DB role. |

## 2. Critical frontend corrections

| Task | Priority | Affected files/approach | Dependencies | Acceptance and verification |
|---|---|---|---|---|
| R-05 Clipboard error feedback | P2 | Add shared clipboard utility; update Events and WorkflowDetail handlers. | None | **Verified 2026-10-31:** shared helper used across event/workflow/incident pages; success and rejection tests pass. |
| R-06 Frontend CI | P2 | Extend .github/workflows/ci.yml with npm ci, typecheck, tests, build, dependency audit. | None | **Implemented; local verified 2026-10-31:** typecheck, 20 tests, audit and production build pass locally; remote job and branch-policy result pending. |
| R-07 UI regression/accessibility checks | P2 | Extend frontend tests for direct/deep routes, batch/invalid form, terminal polling, mobile overflow and axe. | R-06 | **Partially improved 2026-10-31:** authenticated System Health data rendering is now covered; browser viewport and automated accessibility checks remain open. |

## 3. Frontend/backend integration fixes

| Task | Priority | Technical approach | Dependencies | Acceptance |
|---|---|---|---|---|
| R-08 Event collection API | P1 | Add tenant-scoped GET list with page/filter/search, OpenAPI, serializers/tests; replace session-only pseudo-list. | None | **Verified 2026-10-30:** historical events across sessions, tenant isolation, search/type/date filters, pagination, response minimization, frontend integration, live API checks, and live OpenAPI parameters pass. |
| R-09 Incident read/list API | P1 | Add tenant-scoped summary list/detail, then route UI history/detail to persisted IDs. | Existing summary retention model | **Verified 2026-10-31:** live failed workflow analysis persisted, listed and retrieved; search/state filters and pagination documented; cross-tenant detail 404 and list empty; frontend opens persisted analysis by ID. |
| R-10 Analytics HTTP API | P1 | Expose bounded read-only query contract and latest/oldest timestamps/lag; update frontend charts/time filters. | Restore ClickHouse; API design | **Verified 2026-10-31:** tenant PostgreSQL lifecycle endpoint now serves ordinary authenticated clients; privileged ClickHouse global endpoint remains 403 without capability and reports eventual consistency when allowed. Live ClickHouse suite: 5 passed. Analytics page identifies data source/consistency. |
| R-11 Safe health summary | P2 | Add bounded dependency probes or BFF-derived health status; keep metrics token private. | Security review and timeout semantics | **Partially verified 2026-10-31:** live dependency and worker metrics endpoint probes, health timestamps, queue depth and API request/latency values pass; missing series are null and LLM is explicitly not checked. The System Health page’s missing Vite proxy and missing bearer-token forwarding were fixed; route-navigation and service-card tests pass. Worker readiness remains a separate gap. |
| R-12 Production auth model | P2 | For production user-facing use, replace pasted machine token with BFF/session and user/tenant authorization; or constrain current demo. | Product identity model | Browser does not receive reusable privileged machine credential. |

## 4. Missing functionality and contract decisions

| Task | Priority | Description | Dependencies | Acceptance |
|---|---|---|---|---|
| R-13 Idempotency mismatch | P3 | Decide same key/different body result (return existing vs 409 conflict), document and test. | API/product decision | **Verified 2026-10-31:** key-based replay returns original record, tested for changed body, and documented for clients. |
| R-14 Trace semantics | P2 | Decide whether log correlation is enough or true spans required. | Operational objectives | **MVP boundary documented:** request/correlation identifiers are logged across services; distributed spans/export are deferred until justified by operational objectives. |
| R-15 Count snapshot/request cost | P2 | Measure request pattern safely; consider aggregate response if necessary. | API decision; no load test until M6 gate | **Verified 2026-10-31:** overview uses a bounded tenant-scoped aggregate API for KPIs, recent rows, activity and outbox counts; no sampled workflow page fan-out. |

## 5. Test coverage and verification

| Task | Priority | Description | Dependencies | Acceptance |
|---|---|---|---|---|
| R-16 Authenticated frontend/backend smoke | P1 | Automate event create → detail → workflow polling against disposable services. | R-01/R-02/R-08 | **Implemented; local live verification passed 2026-10-31:** `test_end_to_end_live.py` completed against real Kafka/RabbitMQ with one terminal attempt; test creates/revokes temporary credential. CI integration job provisions required topics/services and invokes the test, including an isolated PostgreSQL-settings run. Remote CI execution remains pending, so register status is partially verified. |
| R-17 Real broker failure recovery | P1 | Extend integration coverage for outbox backlog/drain, Rabbit redelivery, worker crash and ClickHouse replay. | R-01 and CI service stack | **Verified locally 2026-10-31:** authenticated broker smoke injects one outbox retry then drains through Kafka, simulates worker crash after DB commit and before ack, confirms Rabbit re-delivery/idempotent attempt count; ClickHouse integration replay test verifies one `FINAL` row after commit interruption. Manual SIGKILL/requeue and dependency outage results are in `docs/operations-runbook.md`. CI result is pending. |
| R-18 OpenAPI contract test | P2 | Add missing workflow state filter and common error response components to schema, then check frontend service paths/methods/types against it. | Stable error schema | **Implemented and locally tested 2026-10-31:** contract test asserts workflow state, bearer scheme and common error envelope; served API rebuilt. |
| R-19 Security scans | P2 | Run npm audit and retrieve actual CI/pip-audit/Trivy results; triage issues. | R-06 | **Partially verified 2026-10-31:** npm audit reports 0 vulnerabilities and CI scan step is configured; remote Python/image and frontend workflow results unavailable. |

## 6. Security and reliability

| Task | Priority | Description | Dependencies | Acceptance |
|---|---|---|---|---|
| R-20 Deny-by-default DRF | P2 | Tighten global API permission/auth defaults; explicitly allow public health/schema routes. | Update tests/docs | **Verified 2026-10-31:** global defaults require API client auth; route tests confirm protected endpoints return 401 while intended health/metrics exceptions retain their explicit policy. |
| R-21 Production CORS | P2 | Configure allowlisted frontend origin at chosen gateway and test preflight/auth headers. | Deployment origin known | No wildcard credentialed CORS; deployed browser requests succeed. |
| R-22 Worker readiness | P2 | Add useful worker readiness/progress probes distinct from process liveness. | Probe semantics | Stopped broker produces actionable not-ready/stale signal. |
| R-23 Redaction tests | P3 | Extend domain-specific secret formats while keeping raw payloads out of logs. | Secret pattern inventory | Known sensitive patterns redacted in tests. |

## 7. Documentation and portfolio readiness

| Task | Priority | Description | Dependencies | Acceptance |
|---|---|---|---|---|
| R-24 Refresh main README | P2 | Align claims with event/incident/analytics API availability and actual CI. | API decisions | **Updated 2026-10-31:** README documents frontend start, API configuration, auth limitations, analytics source behavior and test commands. Remote CI status remains pending. |
| R-25 Current screenshots | P2 | Capture fresh pages after visual review using safe demo data and record viewport. | UI audit and test data | Screenshots match current UI, contain no secrets/customer payload. |
| R-26 Record live drill evidence | P2 | Update runbook/test report with exact executed outputs after drills. | R-02/R-03 | Commands, states, recovery and limitations recorded. |

## 8. M6 readiness

**Do not start M6 until P1 items are closed or formally accepted, the distributed stack and authenticated path are verified, and frontend/API product contracts are decided.** Then write measurable M6 criteria for target Kubernetes environment, secret/network design, resource/replica assumptions, SLO/load profile, observability, rollback and cost limits. The supplied backend master instruction mentions Kubernetes but does not define M6 acceptance. Do not perform load/performance testing before those criteria and an isolated environment are approved.
