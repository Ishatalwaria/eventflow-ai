"""Shared structured-log context and low-cardinality application metrics."""

from contextlib import contextmanager
from contextvars import ContextVar

from prometheus_client import Counter, Gauge, Histogram

_LOG_CONTEXT = ContextVar("eventflow_log_context", default=None)

HTTP_REQUESTS = Counter(
    "eventflow_http_requests_total", "HTTP requests served", ["method", "route", "status"]
)
WORKFLOW_ATTEMPTS = Counter(
    "eventflow_workflow_attempts_total", "Persisted workflow attempts", ["stage", "outcome"]
)
WORKFLOW_RETRIES = Counter(
    "eventflow_workflow_retries_total", "Workflow attempts scheduled for retry", ["stage"]
)
WORKFLOW_DEAD_LETTERS = Counter(
    "eventflow_workflow_dead_letters_total",
    "Tasks routed to the RabbitMQ dead-letter queue",
    ["stage", "error_code"],
)
OUTBOX_PUBLISHES = Counter(
    "eventflow_outbox_publish_total", "Outbox publish outcomes", ["result", "error_code"]
)
OUTBOX_UNPUBLISHED = Gauge(
    "eventflow_outbox_unpublished_messages", "Outbox messages not yet published"
)
OUTBOX_OLDEST_AGE = Gauge(
    "eventflow_outbox_oldest_unpublished_age_seconds", "Age of oldest pending outbox message"
)
BROKER_OPERATIONS = Counter(
    "eventflow_broker_operations_total",
    "Broker operation outcomes",
    ["broker", "operation", "result"],
)
ANALYTICS_DELIVERIES = Counter(
    "eventflow_analytics_deliveries_total", "Lifecycle projection outcomes", ["result"]
)
INCIDENT_PROVIDER_CALLS = Counter(
    "eventflow_incident_provider_calls_total",
    "Incident provider calls",
    ["provider", "result", "error_code"],
)
INCIDENT_PROVIDER_LATENCY = Histogram(
    "eventflow_incident_provider_latency_seconds",
    "Incident provider request latency",
    ["provider"],
    buckets=(0.1, 0.25, 0.5, 1, 2.5, 5, 10, 20, 30, 45, 60, 90),
)
RABBIT_QUEUE_MESSAGES = Gauge(
    "eventflow_rabbitmq_queue_messages",
    "Last sampled message depth; -1 means unavailable",
    ["queue"],
)


@contextmanager
def bind_log_context(**values):
    """Add safe correlation fields for logs in the current request/message scope."""
    context = {
        **(_LOG_CONTEXT.get() or {}),
        **{key: value for key, value in values.items() if value},
    }
    token = _LOG_CONTEXT.set(context)
    try:
        yield
    finally:
        _LOG_CONTEXT.reset(token)


def current_log_context():
    return _LOG_CONTEXT.get() or {}
