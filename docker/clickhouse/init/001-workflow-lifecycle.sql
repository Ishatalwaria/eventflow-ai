CREATE TABLE IF NOT EXISTS eventflow.workflow_lifecycle_facts
(
    lifecycle_id UUID,
    event_id UUID,
    workflow_id UUID,
    event_time DateTime64(3, 'UTC'),
    event_date Date MATERIALIZED toDate(event_time),
    event_type LowCardinality(String),
    stage LowCardinality(String),
    status LowCardinality(String),
    duration_ms Nullable(UInt32),
    attempt_number UInt16,
    error_code LowCardinality(String),
    correlation_id String,
    ingested_at DateTime64(3, 'UTC') DEFAULT now64(3)
)
ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYYYYMM(event_date)
ORDER BY (event_date, workflow_id, event_time, lifecycle_id);
