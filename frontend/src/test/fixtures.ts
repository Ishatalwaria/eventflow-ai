import type { EventDetail, IncidentSummary, Workflow } from "../api/types";

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
