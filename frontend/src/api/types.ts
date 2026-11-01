export type WorkflowState =
  | "RECEIVED"
  | "QUEUED"
  | "PROCESSING"
  | "RETRY_WAIT"
  | "SUCCEEDED"
  | "FAILED"
  | "DEAD_LETTERED";

export type AttemptOutcome = "STARTED" | "SUCCEEDED" | "RETRYING" | "FAILED" | "DEAD_LETTERED";

export interface WorkflowAttempt {
  id: string;
  stage: string;
  attempt_number: number;
  outcome: AttemptOutcome;
  started_at: string;
  finished_at: string | null;
  duration_ms: number | null;
  error_code: string;
  error_detail: string;
}

export interface Workflow {
  id: string;
  event_id: string;
  workflow_type: string;
  state: WorkflowState;
  current_stage: string;
  created_at: string;
  updated_at: string;
  started_at: string | null;
  finished_at: string | null;
  last_error_code: string;
  attempts: WorkflowAttempt[];
}

export interface Paginated<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface EventEnvelope {
  event_type: string;
  schema_version: number;
  source: string;
  idempotency_key: string;
  occurred_at: string;
  correlation_id: string;
  payload: {
    order_id: string;
    currency: string;
    total_minor_units: number;
    items: Array<{ sku: string; quantity: number }>;
  };
}

export interface EventAcceptance {
  event_id: string;
  workflow_id: string;
  workflow_state: WorkflowState;
  duplicate: boolean;
}

export interface EventBatchResponse {
  results: EventAcceptance[];
}

export interface EventDetail {
  id: string;
  event_type: string;
  schema_version: number;
  source: string;
  idempotency_key: string;
  occurred_at: string;
  correlation_id: string;
  request_id: string;
  received_at: string;
  payload: EventEnvelope["payload"];
  workflow: {
    id: string;
    state: WorkflowState;
    current_stage: string;
    created_at: string;
    updated_at: string;
  };
}

export interface EventListItem {
  id: string;
  event_type: string;
  schema_version: number;
  source: string;
  idempotency_key: string;
  correlation_id: string;
  received_at: string;
  workflow: EventDetail["workflow"];
}

export interface IncidentSummary {
  id: string;
  workflow_id: string;
  evidence_hash: string;
  evidence: {
    workflow_id: string;
    time_window: { start: string; end: string };
    truncated: boolean;
    evidence: Array<{ id: string; kind: string; data: Record<string, unknown> }>;
  };
  summary: {
    headline: string;
    confirmed_facts: Array<{ statement: string; evidence_ids: string[] }>;
    hypotheses: Array<{ statement: string; evidence_ids: string[]; confidence: number }>;
    unknowns: string[];
    recommended_checks: string[];
    insufficient_evidence: boolean;
  };
  prompt_version: string;
  provider: string;
  model: string;
  latency_ms: number;
  input_tokens: number | null;
  output_tokens: number | null;
  created_at: string;
}

export interface IncidentSummaryListItem {
  id: string;
  workflow_id: string;
  event_id: string;
  workflow_state: WorkflowState;
  headline: string;
  provider: string;
  model: string;
  created_at: string;
}

export interface LifecycleAnalytics {
  date_from: string;
  date_to: string;
  source: "clickhouse" | "postgresql";
  consistency: "eventually_consistent" | "current_state";
  generated_at: string;
  data_lag_seconds: number | null;
  oldest_event_time: string | null;
  latest_event_time: string | null;
  processed_per_minute: Array<{ minute: string; count: number }>;
  success_count: number;
  failure_count: number;
  success_rate: number;
  failure_rate: number;
  latency_ms: { p50: number | null; p95: number | null; p99: number | null };
  retry_count_distribution: Array<{ retry_count: number; workflow_count: number }>;
  frequent_error_codes: Array<{ error_code: string; count: number }>;
  failure_rate_by_stage: Array<{ stage: string; failures: number; terminal_count: number; failure_rate: number }>;
}

export interface OverviewSummary {
  generated_at: string;
  event_count: number;
  processed_event_count: number;
  workflow_state_counts: Record<WorkflowState, number>;
  average_processing_latency_ms: number | null;
  processed_per_minute: Array<{ minute: string; count: number }>;
  recent_events: Array<Pick<EventListItem, "id" | "event_type" | "source" | "schema_version" | "idempotency_key" | "correlation_id" | "received_at"> & { workflow_id: string | null; workflow_state: WorkflowState | null }>;
  recent_workflows: Array<Pick<Workflow, "id" | "event_id" | "state" | "current_stage" | "created_at" | "updated_at" | "started_at" | "finished_at"> & { attempt_count: number }>;
  outbox_pending_count: number;
  outbox_dead_lettered_count: number;
}

export interface ApiError {
  error: {
    code: string;
    message: string;
    request_id: string | null;
    details: unknown;
  };
}

export interface HealthResponse {
  status: "ok" | "ready" | "not_ready";
  checks?: Record<string, string>;
}

export interface ServiceHealthItem {
  name: string;
  status: "healthy" | "unavailable" | "not_checked";
  last_checked: string | null;
  detail: string;
}

export interface OperationalHealthMetrics {
  api_requests_total: number | null;
  api_average_latency_ms: number | null;
  worker_attempts_total: number | null;
  retry_count: number | null;
  dead_letter_count: number | null;
  llm_error_count: number | null;
  llm_average_latency_ms: number | null;
  task_queue_depth: number | null;
  dead_letter_queue_depth: number | null;
  availability: "available" | "unavailable";
  detail?: string;
}

export interface ServiceHealthSummary {
  generated_at: string;
  services: ServiceHealthItem[];
  metrics: OperationalHealthMetrics;
}

export const WORKFLOW_STATES: WorkflowState[] = [
  "RECEIVED", "QUEUED", "PROCESSING", "RETRY_WAIT", "SUCCEEDED", "FAILED", "DEAD_LETTERED",
];
