import type { EventDetail, EventListItem, IncidentSummary, IncidentSummaryListItem, LifecycleAnalytics, OverviewSummary, ServiceHealthSummary, Workflow } from "../api/types";

export const eventDetailFixture: EventDetail = {
  id: "event-001",
  event_type: "order.created",
  schema_version: 1,
  source: "checkout-web",
  idempotency_key: "idempotency-001",
  occurred_at: "2026-10-30T10:00:00Z",
  correlation_id: "correlation-001",
  request_id: "request-001",
  received_at: "2026-10-30T10:01:00Z",
  payload: { order_id: "order-001", currency: "INR", total_minor_units: 1234, items: [{ sku: "SKU-1", quantity: 1 }] },
  workflow: { id: "workflow-001", state: "FAILED", current_stage: "order_validation", created_at: "2026-10-30T10:01:00Z", updated_at: "2026-10-30T10:02:00Z" },
};

export const eventListFixture: EventListItem = {
  id: eventDetailFixture.id,
  event_type: eventDetailFixture.event_type,
  schema_version: eventDetailFixture.schema_version,
  source: eventDetailFixture.source,
  idempotency_key: eventDetailFixture.idempotency_key,
  correlation_id: eventDetailFixture.correlation_id,
  received_at: eventDetailFixture.received_at,
  workflow: eventDetailFixture.workflow,
};

export const failedWorkflowFixture: Workflow = {
  id: "workflow-001",
  event_id: "event-001",
  workflow_type: "event_processing",
  state: "FAILED",
  current_stage: "order_validation",
  created_at: "2026-10-30T10:01:00Z",
  updated_at: "2026-10-30T10:02:00Z",
  started_at: "2026-10-30T10:01:10Z",
  finished_at: "2026-10-30T10:02:00Z",
  last_error_code: "INVALID_ORDER",
  attempts: [{ id: "attempt-001", stage: "order_validation", attempt_number: 1, outcome: "FAILED", started_at: "2026-10-30T10:01:10Z", finished_at: "2026-10-30T10:02:00Z", duration_ms: 500, error_code: "INVALID_ORDER", error_detail: "Invalid email person@example.com, password=hunter2" }],
};

export const incidentSummaryFixture: IncidentSummary = {
  id: "incident-001",
  workflow_id: "workflow-001",
  evidence_hash: "hash-001",
  evidence: { workflow_id: "workflow-001", time_window: { start: "2026-10-29T10:00:00Z", end: "2026-10-30T10:02:00Z" }, truncated: false, evidence: [
    { id: "workflow:workflow-001", kind: "workflow_state", data: { state: "FAILED", failed_stage: "order_validation" } },
    { id: "attempt:attempt-001", kind: "workflow_attempt", data: { stage: "order_validation", outcome: "FAILED", error_code: "INVALID_ORDER" } },
    { id: "health-metrics:workflow-001", kind: "health_metrics_availability", data: { available: false, detail: "No workflow-correlated health metrics are available." } },
  ] },
  summary: { headline: "Order validation rejected the request", confirmed_facts: [{ statement: "The workflow failed during order validation.", evidence_ids: ["workflow:workflow-001", "attempt:attempt-001"] }], hypotheses: [{ statement: "A required order field may be invalid.", evidence_ids: ["attempt:attempt-001"], confidence: 0.82 }], unknowns: ["The source of the invalid field is unknown."], recommended_checks: ["Review the submitted event contract."], insufficient_evidence: false },
  prompt_version: "v1",
  provider: "test-provider",
  model: "test-model",
  latency_ms: 100,
  input_tokens: 10,
  output_tokens: 20,
  created_at: "2026-10-30T10:03:00Z",
};

export const incidentListFixture: IncidentSummaryListItem = {
  id: incidentSummaryFixture.id,
  workflow_id: incidentSummaryFixture.workflow_id,
  event_id: eventDetailFixture.id,
  workflow_state: "FAILED",
  headline: incidentSummaryFixture.summary.headline,
  provider: incidentSummaryFixture.provider,
  model: incidentSummaryFixture.model,
  created_at: incidentSummaryFixture.created_at,
};

export const lifecycleAnalyticsFixture: LifecycleAnalytics = {
  date_from: "2026-10-24",
  date_to: "2026-10-30",
  source: "postgresql",
  consistency: "current_state",
  generated_at: "2026-10-30T12:00:00Z",
  data_lag_seconds: 45,
  oldest_event_time: "2026-10-29T10:00:00Z",
  latest_event_time: "2026-10-30T11:59:15Z",
  processed_per_minute: [{ minute: "2026-10-30T11:59:00Z", count: 3 }],
  success_count: 2,
  failure_count: 1,
  success_rate: 2 / 3,
  failure_rate: 1 / 3,
  latency_ms: { p50: 12, p95: 30, p99: 45 },
  retry_count_distribution: [{ retry_count: 1, workflow_count: 2 }],
  frequent_error_codes: [{ error_code: "INSUFFICIENT_INVENTORY", count: 1 }],
  failure_rate_by_stage: [{ stage: "order_validation", failures: 1, terminal_count: 3, failure_rate: 1 / 3 }],
};

export const overviewFixture: OverviewSummary = {
  generated_at: "2026-10-31T12:00:00Z",
  event_count: 1,
  processed_event_count: 1,
  workflow_state_counts: { RECEIVED: 0, QUEUED: 0, PROCESSING: 0, RETRY_WAIT: 0, COMPENSATING: 0, SUCCEEDED: 0, FAILED: 1, DEAD_LETTERED: 0, CANCELLED: 0 },
  average_processing_latency_ms: 900,
  processed_per_minute: [{ minute: "2026-10-31T11:59:00Z", count: 1 }],
  recent_events: [{ id: eventListFixture.id, event_type: eventListFixture.event_type, source: eventListFixture.source, schema_version: eventListFixture.schema_version, idempotency_key: eventListFixture.idempotency_key, correlation_id: eventListFixture.correlation_id, received_at: eventListFixture.received_at, workflow_id: eventDetailFixture.workflow.id, workflow_state: "FAILED" }],
  recent_workflows: [{ id: failedWorkflowFixture.id, event_id: failedWorkflowFixture.event_id, state: failedWorkflowFixture.state, current_stage: failedWorkflowFixture.current_stage, created_at: failedWorkflowFixture.created_at, updated_at: failedWorkflowFixture.updated_at, started_at: failedWorkflowFixture.started_at, finished_at: failedWorkflowFixture.finished_at, attempt_count: 1 }],
  outbox_pending_count: 0,
  outbox_dead_lettered_count: 0,
};

export const serviceHealthFixture: ServiceHealthSummary = {
  generated_at: "2026-10-31T12:00:00Z",
  services: [
    { name: "Django API", status: "healthy", last_checked: "2026-10-31T12:00:00Z", detail: "Authenticated health summary responded." },
    { name: "PostgreSQL", status: "healthy", last_checked: "2026-10-31T12:00:00Z", detail: "Dependency probe succeeded." },
    { name: "Kafka", status: "unavailable", last_checked: "2026-10-31T12:00:00Z", detail: "Dependency probe failed." },
    { name: "LLM provider", status: "not_checked", last_checked: null, detail: "Provider is not called during health checks." },
  ],
  metrics: {
    api_requests_total: 12,
    api_average_latency_ms: 10.5,
    worker_attempts_total: 4,
    retry_count: 1,
    dead_letter_count: 0,
    llm_error_count: 0,
    llm_average_latency_ms: null,
    task_queue_depth: 2,
    dead_letter_queue_depth: 0,
    availability: "available",
  },
};
