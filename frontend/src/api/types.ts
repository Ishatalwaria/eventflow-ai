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

export const WORKFLOW_STATES: WorkflowState[] = [
  "RECEIVED", "QUEUED", "PROCESSING", "RETRY_WAIT", "SUCCEEDED", "FAILED", "DEAD_LETTERED",
];
