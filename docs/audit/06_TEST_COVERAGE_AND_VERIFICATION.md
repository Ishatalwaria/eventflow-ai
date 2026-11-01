# 06 — Test coverage and verification

## Commands executed

| Exact command | Result | Notes |
|---|---|---|
| .\.venv314\Scripts\python.exe -m pytest -q | PASS: 88 passed, 4 skipped, 2.64s | PostgreSQL concurrency skipped; ClickHouse test requires EVENTFLOW_RUN_CLICKHOUSE_INTEGRATION=1; two broker tests require EVENTFLOW_RUN_BROKER_INTEGRATION=1. |
| .\.venv314\Scripts\ruff.exe check . | PASS | All checks passed. |
| .\.venv314\Scripts\ruff.exe format --check . | PASS | 116 files already formatted. |
| .\.venv314\Scripts\python.exe manage.py check | PASS | No issues. |
| .\.venv314\Scripts\python.exe manage.py makemigrations --check --dry-run | PASS with warning | No changes detected. Django could not verify DB migration history due local socket access denied; readiness API separately confirmed PostgreSQL. |
| docker compose config --quiet | PASS | Docker Desktop access was granted. |
| docker compose ps -a | Executed, partial stack stopped | API/DB healthy; Kafka/RabbitMQ/ClickHouse exited 255. |
| GET /health/live | PASS, 200 status ok | Live HTTP. |
| GET /health/ready | PASS, 200 ready/database ok | Live DB query through API. |
| GET /api/schema/?format=json | PASS, OpenAPI 3.0.3 | Expected paths and ClientBearer scheme. |
| GET /api/v1/workflows without auth | Expected 401 | Common error envelope. |
| npm run typecheck from frontend | PASS | TypeScript project check. |
| npm test from frontend | PASS: 11 tests, 3 files | API services mocked; not backend integration. |
| npm run build from frontend | PASS | TypeScript + Vite production build. Two non-fatal Rollup annotation warnings originated in Zod package comments. |

Bare pytest/ruff/python first failed because shell PATH did not expose those commands; repository venv executables succeeded. Initial direct local HTTP requests were denied by restricted-shell socket policy; live requests were rerun with local service access.

## Test coverage present

Backend tests cover event validation/auth/idempotency/rollback/tenant scope/pagination; common health/logging/metrics auth; outbox; workflow state/attempt/retry/idempotency; simulated pipeline and broker failures; fake ClickHouse sink/offset ordering; evidence redaction/window/limits; provider HTTP contracts/errors; incident API auth/rate/error behavior.

Frontend tests cover navigation, event list/submission, workflow details, incident facts/hypotheses, analytics unavailable state, common loading/empty states, API error/401 handling and health display.

## CI configuration versus execution

.github/workflows/ci.yml defines Ruff, Django/migration checks, pytest, pip-audit, PostgreSQL concurrency, live Kafka/Rabbit/ClickHouse tests and Trivy. No GitHub Actions result was retrieved. The workflow does not build/test frontend.

## Not run or blocked

- PostgreSQL concurrency test skipped by default; no isolated database-creation role configured for this run.
- Live broker/ClickHouse tests skipped; those Compose services were exited.
- Authenticated event create/detail, workflow retrieval and incident analysis: no client token used.
- Live OpenAI/Gemini call: not attempted.
- Docker stop/restore failure drills: not run; audit was read-only.
- ESLint: not configured.
- Frontend dependency audit and CI result: not run/retrieved.
- Kubernetes/performance/load tests: intentionally not run; M6 deferred.

## High-value missing tests

1. Concurrent duplicate race in isolated PostgreSQL.
2. Real event accepted with Kafka down, outbox accumulation, then drain after restore.
3. Kafka-to-Rabbit-to-worker terminal flow and worker crash/redelivery after commit.
4. ClickHouse outage/replay after restore with unique seeded facts.
5. Valid two-client tenant isolation at HTTP boundary.
6. Browser invalid/batch form, revoked token, pagination/filter and terminal polling behavior.
7. Responsive overflow and automated accessibility checks.

Passing unit tests are not evidence that these distributed journeys succeeded.

## Implementation verification update (2026-10-31)

| Check | Result |
|---|---|
| Backend analytics API, sink and event API tests | 25 passed, 2 skipped (PostgreSQL-only race and opt-in test not selected in this invocation). |
| Live ClickHouse seeded integration | 4 passed; seeded success/failure/rate/latency/retry/error/stage queries matched expected values. |
| Frontend typecheck | Passed. |
| Frontend tests | 16 passed across 3 files, including analytics charts, time range, manual refresh and permission denial. |
| Frontend production build | Passed; Vite reported two non-fatal dependency comment-annotation warnings in Zod. |
| Analytics HTTP verification | Seeded date returned 200 and actual ClickHouse values (`success=1`, `failure=1`) with `eventually_consistent`; ordinary client returned 403. Temporary clients revoked. |
| Live local failure drills | Kafka, RabbitMQ, worker queue/in-flight redelivery, and ClickHouse replay passed; provider safe-failure API test passed. Final Compose services healthy where health checks are configured; outbox had zero unpublished and dead-lettered rows. |
| Authenticated broker workflow smoke | `test_end_to_end_live.py`: 1 passed against live Kafka/RabbitMQ. It exercises authenticated event create/detail, an injected outbox failure and real Kafka drain, Rabbit task forwarding, commit-before-ack redelivery, idempotent single attempt, and terminal workflow retrieval. |
| ClickHouse offset-replay integration | `test_sink.py`: 5 passed with live ClickHouse; replay after simulated commit interruption produced one final lifecycle fact. |
| Final default backend checks after integration additions | 96 passed, 6 skipped; Ruff lint/format and Django system checks passed. Migration check reported no changes; host-side migration history probe warns because local TCP access is restricted. The Compose API confirms migration `0002_apiclient_can_view_analytics` applied. |
| Final frontend checks | Typecheck passed; 16 tests passed; production build passed with two non-fatal Zod Rollup annotation warnings. |

Limitations: failure drills ran only against the local Compose environment. The Kafka topic-init command timed out once during restart; direct broker inspection confirmed all required topics existed and the outbox/workflow recovered. The R-16 live smoke is wired into CI, but its remote CI result has not yet been observed. EF-01 remains partially open because the trigger for the earlier coordinated container stop cannot be determined from retained evidence.
