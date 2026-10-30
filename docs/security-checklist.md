# EventFlow AI security checklist

Use this checklist before a production deployment and after credential or infrastructure changes.

## Application and API

- [ ] Run with `DEBUG=false`, a unique `DJANGO_SECRET_KEY`, explicit `ALLOWED_HOSTS`, and TLS at the trusted ingress.
- [ ] Keep `.env` and deployment secrets out of source control. Use a secret manager for production values.
- [ ] Give the API database role only required table DML and sequence access. Use a separate migration role; do not grant the API role `CREATEDB`, `CREATEROLE`, or ownership.
- [ ] Create one API client credential per integration. Store only the hash, restrict ownership, rotate exposed credentials, and revoke unused clients.
- [ ] Keep event request limits, batch limits, pagination, dependency timeouts, and incident-summary rate limits enabled.
- [ ] Keep `/metrics` on a private network. In production set a random `METRICS_TOKEN` of at least 32 characters and send it only as `X-Metrics-Token` to the scraper.
- [ ] Treat request bodies, logs, broker messages, and provider responses as untrusted. Do not log raw payloads, headers, API tokens, or provider keys.
- [ ] Review evidence redaction and the saved evidence snapshot before changing what is sent to the LLM.
- [ ] Keep LLM tools disabled. The incident assistant must not mutate workflow state or execute commands/queries.

## Data stores and brokers

- [ ] Use TLS for PostgreSQL, Kafka, RabbitMQ, ClickHouse, and provider traffic in production.
- [ ] Use dedicated non-default RabbitMQ, Kafka, and ClickHouse identities with only required permissions.
- [ ] Keep Kafka topic ACLs, consumer groups, and retention aligned with the deployment's recovery objectives.
- [ ] Restrict ClickHouse to analytics writes/reads; PostgreSQL remains the source of truth for workflow state.
- [ ] Protect and back up PostgreSQL and broker data according to recovery objectives. Test restore procedures.
- [ ] Inspect outbox age and RabbitMQ ready-message depth during incidents; do not delete pending messages to clear a backlog.

## Build and release

- [ ] Regenerate dependency locks intentionally with the pinned `uv` version and review `uv.lock` changes.
- [ ] Require CI lint, API/unit tests, PostgreSQL/broker/ClickHouse integration tests, `pip-audit`, and the Trivy image scan before release.
- [ ] Verify the application image runs as UID/GID 10001 and contains no `.env`, source credentials, or development-only packages.
- [ ] Review high/critical scan findings and document any accepted, time-bounded exception before deployment.
- [ ] Run database migrations as the migration identity before rolling out API and worker code.
