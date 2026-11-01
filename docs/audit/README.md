# EventFlow AI engineering audit

**Audit date:** 2026-10-30  
**Scope:** Read-only review of the repository against the backend master instructions through M5, frontend master instructions and phases 0–8, and final UI consistency prompt. M6 was not implemented or exercised.

**Implementation update (2026-10-31):** Tenant-scoped PostgreSQL analytics for ordinary authenticated clients, an overview aggregate, and safe service-health summaries were implemented. Global ClickHouse analytics remains capability-gated. The System Health page’s missing Vite proxy was fixed. A second issue was found: the Axios interceptor omitted bearer auth for `/health/services`, causing a 401 that cleared the token; the protected path is now authorized and navigation, service-card, and permission-detail tests cover the fix. Global analytics access guidance is shown in Settings and on a 403. Current verification: 101 backend tests passed (6 integration/concurrency skips), 25 frontend tests passed, typecheck/build, Ruff, and Django checks passed; ClickHouse suite 5 passed. EF-01’s coordinated service-stop cause and remote CI results remain unverified; Stage 2 remains open.

## Overall assessment

EventFlow AI has a coherent MVP architecture and meaningful backend correctness coverage: client-authenticated, tenant-scoped event and workflow APIs; PostgreSQL transactions and uniqueness; transactional outbox; at-least-once broker flow; workflow attempt persistence; ClickHouse projection code; bounded incident evidence; and production-oriented configuration. The React app uses the actual API contract where available and accurately discloses missing browser capabilities.

Several end-to-end paths are now verified against the running distributed stack, including authenticated event-to-workflow processing, event/incident retrieval, tenant/global analytics authorization and data projection, health summaries, and local failure/recovery drills. Remaining verification gaps are the unknown cause of the earlier coordinated stop, PostgreSQL concurrency (still skipped in the default suite), production identity/authentication, remote CI status, browser-level accessibility/responsive coverage, and third-party provider behavior.

## Completion assessment

| Area | Assessment |
|---|---|
| Backend M0 | Mostly implemented; Django checks pass. The running Compose database confirms both common migrations applied. The host-side migration-history check still warns because its local socket permission is restricted. |
| Backend M1 | Implemented and unit/API-tested. Live tenant-authenticated event write/read, workflow completion, idempotent replay, event listing and incident isolation were verified; PostgreSQL concurrency remains unverified. |
| Backend M2 | Live authenticated event-to-workflow success and failure paths reach terminal states; Kafka/RabbitMQ round-trip and documented local failure/recovery drills passed. |
| Backend M3 | ClickHouse schema, sink, bounded capability-gated global API and charts exist. Tenant-scoped PostgreSQL analytics now serves regular authenticated clients; live ClickHouse/API path passed. |
| Backend M4 | Evidence builder, provider adapters, validation and persistence exist; tenant-scoped incident list/detail and live local analysis retrieval are verified. Third-party provider behavior remains unverified. |
| Backend M5 | Logging, metrics, production settings, CI, runbook and non-root API image exist. IDs are correlated, but no distributed spans/export are configured. Safe dependency probes and allowlisted metrics exist; worker consumption readiness remains limited. |
| Frontend phases 0–8 | Main routes, API client, forms, monitoring, incident interaction, analytics, health, settings and tests exist. Overview, events, incidents, analytics and service health use backend APIs; the development proxy now forwards the detailed health route; unsupported or unsampled values remain unavailable. |
| UI/UX | Shared enterprise-style UI and recent consistency fixes exist. Fresh visual browser review was not completed during this audit. |
| Integration | Partial. Health/OpenAPI, authenticated event success/failure, broker operations, ClickHouse sink/replay, incident persistence/retrieval, seeded analytics API/access checks, and documented local failure drills are live-verified. The coordinated-stop cause remains unknown. |
| Security | No critical source-level issue was confirmed. Browser bearer credentials remain a development/demo arrangement. See security report. |
| Testing | Current full backend suite: 101 passed/6 skipped; Ruff lint/format and Django checks passed. ClickHouse integration: 5 passed. Frontend: 25 passed; typecheck and production build passed. Authenticated broker smoke passed with local worker paused; remote CI is pending. |

## Findings by priority

Counts are unique records in the [master gap register](07_MASTER_GAP_REGISTER.md).

| Priority | Count |
|---|---:|
| P0 | 0 |
| P1 | 2 open (8 records; EF-02 through EF-06 and EF-21 resolved; EF-01 and EF-20 remain partially verified) |
| P2 | 5 unresolved or partial (production auth, worker readiness, trace depth, browser accessibility/responsive verification, production CORS; other implemented entries await remote checks where applicable) |
| P3 | 1 deferred (M6 acceptance); idempotency semantics resolved |

## Most important unresolved items

1. Retrieve and review remote CI results for the authenticated smoke and frontend jobs.
2. Diagnose the coordinated service stop if it recurs; its original trigger remains unknown.
3. Establish a production-safe browser identity/auth boundary. The current client credential is not an end-user session.
4. Add browser-level accessibility/responsive checks and meaningful worker readiness if required by operations.

## Recommended order

Follow the [implementation roadmap](08_IMPLEMENTATION_ROADMAP.md): restore and verify local services, resolve the API/product contract gaps, establish production-safe frontend auth, expand integration checks and CI, then decide whether M6 prerequisites are satisfied.

## M6 readiness

**Not ready.** The prior coordinated stop trigger is unknown, and the new R-16 CI result has not been observed. Stage 2 is not fully closed while EF-01 and EF-20 remain partially open. The supplied backend master instructions define M0–M5 and mention Kubernetes as a later milestone, but provide no detailed M6 acceptance criteria. Do not start M6 before the remaining P1 gaps are resolved or explicitly accepted.

## Reproduce verification

From repository root (the audit environment had .venv314 installed):

    .\.venv314\Scripts\python.exe -m pytest -q
    .\.venv314\Scripts\ruff.exe check .
    .\.venv314\Scripts\ruff.exe format --check .
    .\.venv314\Scripts\python.exe manage.py check
    .\.venv314\Scripts\python.exe manage.py makemigrations --check --dry-run
    Set-Location frontend
    npm run typecheck
    npm test
    npm run build
    Set-Location ..
    docker compose config --quiet
    docker compose ps -a

Live read-only calls:

    Invoke-RestMethod http://127.0.0.1:8000/health/live
    Invoke-RestMethod http://127.0.0.1:8000/health/ready
    Invoke-RestMethod 'http://127.0.0.1:8000/api/schema/?format=json'

Schema returned OpenAPI 3.0.3 and expected paths. GET /api/v1/workflows without credentials returned 401. Do not place real client tokens, DB credentials or provider keys into audit transcripts.

## Audit documents

- [01 Architecture audit](01_ARCHITECTURE_AUDIT.md)
- [02 Backend gap analysis](02_BACKEND_GAP_ANALYSIS.md)
- [03 Frontend gap analysis](03_FRONTEND_GAP_ANALYSIS.md)
- [04 End-to-end integration audit](04_END_TO_END_INTEGRATION_AUDIT.md)
- [05 Security and reliability audit](05_SECURITY_RELIABILITY_AUDIT.md)
- [06 Test coverage and verification](06_TEST_COVERAGE_AND_VERIFICATION.md)
- [07 Master gap register](07_MASTER_GAP_REGISTER.md)
- [08 Implementation roadmap](08_IMPLEMENTATION_ROADMAP.md)
