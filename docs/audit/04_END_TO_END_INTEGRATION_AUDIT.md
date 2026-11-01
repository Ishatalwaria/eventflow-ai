# 04 — End-to-end integration audit

## Runtime snapshot

docker compose config --quiet succeeded. docker compose ps -a showed API healthy and PostgreSQL healthy; Kafka, RabbitMQ and ClickHouse exited (255). Migration and topic-init one-shot containers exited successfully. Consumer/worker containers were up but recent logs showed DNS/connectivity errors to stopped services. Their Compose healthchecks are disabled, so Up is not a readiness signal.

Live observations:

- GET /health/live → 200, status ok.
- GET /health/ready → 200, ready/database ok.
- GET /api/schema/?format=json → OpenAPI 3.0.3 with expected paths and ClientBearer.
- GET /api/v1/workflows without credentials → 401 common error envelope.

No client credential was supplied, no write request was issued, and no failure drill was run.

## Journey results

| Journey | Trace | Result |
|---|---|---|
| 1. Single event ingestion | Frontend EventsPage validates order.created v1 and calls events service → Axios bearer/request ID → EventCreateView validates → atomic accept_events creates Event + Workflow + OutboxMessage + log → acceptance response. | Implemented and unit/API-tested; live authenticated vertical slice unverified. DB healthy; Kafka not required for initial transaction but this outage behavior was not live exercised. |
| 2. Async processing | Outbox lease/publish → Kafka → consumer validates against DB and publishes persistent Rabbit task before Kafka commit → worker locks workflow and persists attempt/state/lifecycle outbox → ack/reroute → workflow API → polling. | Verified on 2026-10-30/31 for live success (`SUCCEEDED`) and permanent inventory failure (`FAILED`); broker Kafka/Rabbit round-trip checks pass. Controlled outage/recovery drills are still outstanding. |
| 3. Event retrieval | Authenticated event collection → GET event detail → tenant-scoped event/workflow data → event detail route. | Verified 2026-10-30: live create returned 201, detail returned 200, workflow reached `SUCCEEDED`; event collection live checks passed for filters, pagination, tenant isolation and payload minimization. |
| 4. AI incident | Failed workflow → POST summary → bounded evidence → local deterministic provider → strict schema/evidence ID validation → persisted summary → tenant-scoped list/detail → UI evidence investigation. | Verified 2026-10-31 against Compose: real `FAILED` workflow produced a 201 summary; list/detail returned 200; another client received an empty list and 404. Third-party provider behavior remains unverified. |
| 5. Analytics | Lifecycle outbox → Kafka lifecycle topic → consumer → ClickHouse row → analytics_report CLI query. | Backend code present, live blocked; frontend integration missing because no HTTP query endpoint. |
| 6. System health | Public live/readiness → frontend polling. Separate metrics endpoint needs metrics token. | API/PostgreSQL checks live-verified. Health does not check the brokers/ClickHouse/workers/provider; their stopped state was observed through Docker/log access. |
| 7. Failure recovery | Unit injections and manual runbook steps cover selected failure paths. | Not fully run. No controlled stop/restore drill or authenticated event; cannot claim recovery/drain behavior succeeded. |

## Failure scenarios

| Scenario | Evidence | Conclusion |
|---|---|---|
| Kafka unavailable | Outbox retry tests; Kafka exited; consumer logs report failed Kafka resolution. | Retry code exists; no controlled drill or post-restore drain verified. |
| RabbitMQ unavailable | Forwarding commits Kafka after Rabbit confirmation; Rabbit exited; connection retries in logs. | Recovery implementation exists; live delivery after restoration unverified. |
| Worker stopped during task | Unit test covers duplicate/crash after DB commit before ack. | No live worker kill/requeue drill. |
| ClickHouse unavailable | Offset commit occurs only after sink confirmation; fake sink test; ClickHouse exited and analytics consumer logged failures. | Isolated projection failure is designed; replay after restoration not verified. |
| LLM unavailable | Provider/API tests inject errors and preserve workflow state. | No live provider request/outage attempted. |
| Duplicate event | Database uniqueness/savepoint tests. | Sequential duplicate tested; PostgreSQL concurrent case skipped locally. |
| Invalid event | Serializer/API tests. | Automated validation covered; no malformed live request sent. |
| Network interruption | Axios network/timeout mapping tests. | Client error behavior tested; browser interruption not performed. |
| Authentication failure | Live no-auth workflow request 401; frontend 401 unit test. | Negative auth verified; valid auth/tenant separation not live tested. |

## Evidence limits

The Compose services pre-existed this audit; historical state is not inferred. No services were started/stopped, no data was written, and no secrets were accessed. See verification report for exact commands/results.

## Implementation follow-up (2026-10-31)

Subsequent authorized work verified event collection and incident list/detail APIs, including tenant boundaries, and the capability-gated lifecycle analytics endpoint against seeded ClickHouse data. Live failure drills covered Kafka outbox drain, RabbitMQ task handoff, worker queue and in-flight redelivery, ClickHouse replay, and provider failure handling. Exact results are in `docs/operations-runbook.md`. At the end of drills all Compose services were up and `outbox_status` reported zero pending/dead-lettered messages. The prior coordinated container-stop trigger remains unknown; do not infer its cause from recovery.
