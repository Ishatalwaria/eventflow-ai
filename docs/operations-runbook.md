# EventFlow AI operations runbook

This runbook is for the local Docker Compose stack and the equivalent production services. Commands below use PowerShell-compatible Compose commands unless noted. Never run failure drills against production.

## Signals and first checks

1. Check service health and recent logs:

   ```powershell
   docker compose ps
   docker compose logs --since=10m api outbox-publisher kafka-consumer workflow-worker analytics-consumer
   ```

2. Check PostgreSQL readiness and pending Kafka handoff:

   ```powershell
   curl.exe -i http://localhost:8000/health/ready
   docker compose exec -T api python manage.py outbox_status
   ```

3. Inspect Prometheus text metrics. The API endpoint is at `http://localhost:8000/metrics`; worker process endpoints are on ports 9101–9104. Metrics are disabled unless `METRICS_TOKEN` is configured. Generate a random local token in PowerShell, export it before starting Compose, and recreate the services:

   ```powershell
   $env:METRICS_TOKEN = [Convert]::ToBase64String([Security.Cryptography.RandomNumberGenerator]::GetBytes(32))
   docker compose up -d --force-recreate api outbox-publisher kafka-consumer workflow-worker analytics-consumer
   curl.exe -H "X-Metrics-Token: $env:METRICS_TOKEN" http://localhost:8000/metrics
   curl.exe -H "X-Metrics-Token: $env:METRICS_TOKEN" http://localhost:9101/metrics
   curl.exe -H "X-Metrics-Token: $env:METRICS_TOKEN" http://localhost:9102/metrics
   curl.exe -H "X-Metrics-Token: $env:METRICS_TOKEN" http://localhost:9103/metrics
   curl.exe -H "X-Metrics-Token: $env:METRICS_TOKEN" http://localhost:9104/metrics
   ```

   To retain the token between terminal sessions, store the generated value in the ignored local `.env` file as `METRICS_TOKEN=...`, then recreate the same services. Never commit or share that file. The API and worker metrics endpoints reject requests when the token is absent or incorrect.

   - `eventflow_http_requests_total` shows API route and status counts; spikes in 4xx/5xx help distinguish client errors from server failures.
   - `eventflow_outbox_unpublished_messages` and `eventflow_outbox_oldest_unpublished_age_seconds` show stalled PostgreSQL-to-Kafka handoff.
   - `eventflow_workflow_attempts_total`, `eventflow_workflow_retries_total`, and `eventflow_workflow_dead_letters_total` show processing outcomes and exhausted/permanent failures.
   - `eventflow_rabbitmq_queue_messages` samples ready messages on the task, retry, and dead-letter queues. `-1` means the worker cannot sample queue depth; these gauges are not unacked-message counts.
   - `eventflow_incident_provider_latency_seconds` and `eventflow_incident_provider_calls_total` distinguish slow provider calls from provider errors.
   - `eventflow_analytics_deliveries_total` shows ClickHouse projection delivery failures without changing workflow state.

   Worker metrics are process-local and stop being scrapeable if that worker container is down. The API multiprocess registry aggregates Gunicorn workers. Queue gauges show the last successful sample. The `/health/ready` Docker probe applies only to the API; workers rely on process exit/restart status and their broker/queue metrics, rather than an API HTTP probe against a worker process.

4. Follow one request through logs using `request_id`/`trace_id`, then join it to `event_id`, `workflow_id`, and `correlation_id`. These propagated IDs provide cross-service correlation; this release does not export OpenTelemetry spans.

## Recovery and failure drills

Run these drills only against a disposable local stack. Before each drill, submit one valid event and record its returned event/workflow IDs. Verify the indicated state and metrics before restoring the dependency.

### Kafka unavailable: outbox backlog

```powershell
docker compose stop kafka
docker compose exec -T api python manage.py outbox_status
```

Submit another event. The API should still accept it because PostgreSQL and the transactional outbox are authoritative. The unpublished count/age should increase while the outbox publisher records bounded retries. Restore Kafka and re-run topic initialization if needed:

```powershell
docker compose start kafka
docker compose run --rm kafka-init
docker compose logs --since=5m outbox-publisher kafka-consumer
```

Confirm the outbox drains and the workflow advances. Do not delete outbox rows to clear the alert.

### RabbitMQ unavailable: task handoff

```powershell
docker compose stop rabbitmq
```

Submit an event. Kafka-to-Rabbit forwarding should retry and leave the Kafka offset uncommitted when RabbitMQ cannot confirm the task. The workflow should remain unprocessed in PostgreSQL. Restore RabbitMQ and inspect consumer/worker logs and the workflow state:

```powershell
docker compose start rabbitmq
docker compose logs --since=5m kafka-consumer workflow-worker
```

The event should be delivered after reconnection; duplicate Kafka delivery is safe through workflow/task idempotency.

### Worker interrupted during a task

For a non-deterministic local drill, submit several tasks and stop the worker while a delivery is active:

```powershell
docker compose kill -s SIGKILL workflow-worker
docker compose up -d workflow-worker
```

RabbitMQ should redeliver unacknowledged tasks. Inspect workflow attempts and logs for one durable outcome per attempt. The deterministic unit test `test_duplicate_task_and_crash_after_db_commit_are_idempotent` covers the crash-after-commit-before-ack window; a manual kill while idle does not exercise that exact window.

### ClickHouse unavailable: analytics lag

```powershell
docker compose stop clickhouse
```

Submit a valid event and confirm the PostgreSQL workflow still reaches its normal terminal state. The analytics consumer should not commit the lifecycle Kafka offset when ClickHouse insert confirmation fails. Restore ClickHouse and verify the analytics consumer resumes:

```powershell
docker compose start clickhouse
docker compose logs --since=5m analytics-consumer
```

Analytics may lag and duplicate lifecycle delivery is reconciled with the deterministic lifecycle key. Do not use ClickHouse to decide current workflow state.

### LLM provider unavailable: incident-only failure

Incident analysis runs only after the workflow has failed; it is not part of event processing. The automated service/API test injects a transient provider error and verifies that the API returns a safe `503`, does not persist a partial summary, and leaves workflow state unchanged. Do not test outages by exposing real keys or by changing a production provider secret. If a provider is unavailable, inspect the LLM latency/error metrics and retry after the provider recovers.

## Restart and recovery order

1. Restore PostgreSQL first; do not start migrations with the API role.
2. Restore Kafka and create/verify the configured domain and lifecycle topics.
3. Restore RabbitMQ and confirm durable exchanges/queues are declared.
4. Restore the API, publisher, Kafka consumer, worker, and analytics consumer.
5. Confirm outbox age falls, Rabbit ready-message depth is progressing, workflow attempts resume, and ClickHouse freshness advances.

## Automated resilience coverage

Run `uv run --frozen --extra dev pytest -q` for unit/API failure cases and `uv run --frozen --extra dev pytest -m integration -q` with the live local brokers and ClickHouse. The test suite exercises broker unavailable/retry paths, outbox failure/replay, Rabbit redelivery idempotency, ClickHouse failure before offset commit, and provider errors. The manual container stop drills are not claimed as executed by CI unless the corresponding live container job reports success.
