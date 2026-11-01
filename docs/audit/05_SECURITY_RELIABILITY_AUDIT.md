# 05 — Security and reliability audit

Severity reflects source/config risk observed, not a claim of exploitability. No critical source-level issue was confirmed.

## Findings

| ID | Severity | Finding | Impact/evidence | Recommendation |
|---|---|---|---|---|
| SEC-01 | Medium | Browser bearer token is a machine credential kept in JavaScript memory. | auth-token module and Settings; memory-only avoids persistence but does not shield from page scripts or browser operator. | Use server-side BFF/session and user authorization for production user-facing use; keep token paste flow to controlled demos. |
| SEC-02 | Medium | DRF global defaults include AllowAny and Session/Basic; route security relies on each view override. | Current protected views correctly override with client auth/IsAuthenticated; a future endpoint omission could be public. | Set restrictive API defaults and explicit exceptions for intended public routes; test route policy. |
| SEC-03 | Low | Django does not configure CORS. | Local Vite proxy is same-origin; frontend API map assigns production CORS to gateway. | Configure a deployment-origin allowlist and verify preflight/Authorization behavior. |
| SEC-04 | Medium | X-Trace-ID is an alias of request ID; no distributed span export. | Request middleware and runbook; logs can be correlated but not traced with spans. | Document log correlation as MVP or add trace context/export if required. |
| SEC-05 | Low | Redaction is pattern-based. | config/logging.py covers common bearer/password/key labels and email/phone; unusual formats may pass. | Keep payloads out of logs; add domain secret-pattern tests before new logging fields. |
| SEC-06 | Medium | Distributed dependencies are not healthy in current local runtime. | Audit Compose snapshot: Kafka/RabbitMQ/ClickHouse exited; connection retries in worker/consumer logs. | Diagnose exits, restore service health and verify drain/recovery. |
| SEC-07 | Low | Long-running worker/consumer Compose healthchecks are disabled. | Compose; runbook says workers rely on process state/metrics. Up does not mean broker connected or progressing. | Add meaningful readiness/progress probes or watchdog/alert; report unknown separately from healthy. |
| SEC-08 | Low | Frontend dependencies are not audited in CI. | Lockfile exists; GitHub workflow includes Python audit and image scan but no npm scan. | Add lockfile-based npm audit/scanner and triage policy. |

## Controls observed

- Random API client secrets are password-hashed; revocation is enforced.
- Event/workflow/incident reads are scoped to authenticated client.
- Common handler masks unhandled internal details and adds request ID.
- Event body, batch size, DB/provider/broker timeouts, pagination and output size are bounded.
- At-least-once semantics are acknowledged; outbox/workflow records use database idempotency.
- ClickHouse is treated as eventually consistent and not authoritative for workflow state.
- Evidence builder has time/item/text limits, excludes event payload and arbitrary log attributes, sanitizes common credentials/PII and hashes snapshot.
- Providers use structured output, no tools, bounded calls; citations are validated against supplied evidence.
- Metrics require a separate constant-time compared token; production requires a long token and local Compose ports bind to loopback.
- Production settings require explicit hosts, TLS/nonlocal services, strong secrets and production LLM provider; API image uses non-root UID/GID.
- Frontend uses React text/JSON rendering; no dangerouslySetInnerHTML/innerHTML/eval/localStorage usage found.

## Reliability notes

- No exactly-once claim; duplicate broker delivery is handled through DB state and deterministic projection IDs.
- Invalid Kafka domain records are routed to dead-letter before offset commit. Rabbit invalid tasks are dead-lettered before ack. Failed reroutes stay unconfirmed.
- Analytics consumer commits Kafka only after confirmed ClickHouse insert; replay is possible and deterministic lifecycle IDs plus ReplacingMergeTree FINAL address duplicates.
- Worker attempt outcome/state and lifecycle outbox are committed transactionally before ack.
- Current logs evidence retry loops, not successful recovery.

## Deployment-specific checks not proven

Production PostgreSQL grants, TLS roots, Kafka ACLs, Rabbit vhost permissions, ClickHouse user policy, secrets-manager wiring, ingress/CORS, backups/restores and provider secret controls require deployment review. The existing security checklist lists these controls.
