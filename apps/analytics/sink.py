"""ClickHouse projection sink for versioned workflow lifecycle messages."""

import uuid
from datetime import datetime

from django.conf import settings

TABLE = "workflow_lifecycle_facts"
INSERT_COLUMNS = [
    "lifecycle_id",
    "event_id",
    "workflow_id",
    "event_time",
    "event_type",
    "stage",
    "status",
    "duration_ms",
    "attempt_number",
    "error_code",
    "correlation_id",
]


class AnalyticsUnavailable(RuntimeError):
    """ClickHouse could not durably accept an analytical fact."""


def make_analytical_row(event):
    """Map a validated v1 lifecycle envelope to one deterministic fact row."""
    payload = event["payload"]
    workflow_id = str(uuid.UUID(event["workflow_id"]))
    attempt = payload["attempt_number"]
    stage = payload["stage"]
    event_type = event["event_type"]
    identity = f"{workflow_id}:{stage}:{attempt}:{event_type}"
    event_time = datetime.fromisoformat(event["recorded_at"].replace("Z", "+00:00"))
    duration_ms = payload.get("duration_ms")
    return {
        "lifecycle_id": uuid.uuid5(uuid.NAMESPACE_URL, identity),
        "event_id": uuid.UUID(event["event_id"]),
        "workflow_id": uuid.UUID(workflow_id),
        "event_time": event_time,
        "event_type": event_type,
        "stage": stage,
        "status": payload["state"],
        "duration_ms": duration_ms,
        "attempt_number": attempt,
        "error_code": payload.get("error_code", ""),
        "correlation_id": event["correlation_id"],
    }


class ClickHouseLifecycleSink:
    def __init__(self, client=None):
        self.client = client or create_clickhouse_client()

    def write(self, event):
        row = make_analytical_row(event)
        try:
            self.client.insert(
                f"{settings.CLICKHOUSE_DATABASE}.{TABLE}",
                [[row[column] for column in INSERT_COLUMNS]],
                column_names=INSERT_COLUMNS,
            )
        except Exception as exc:
            raise AnalyticsUnavailable("ClickHouse insert was not confirmed.") from exc


def create_clickhouse_client():
    import clickhouse_connect

    return clickhouse_connect.get_client(
        host=settings.CLICKHOUSE_HOST,
        port=settings.CLICKHOUSE_PORT,
        username=settings.CLICKHOUSE_USERNAME,
        password=settings.CLICKHOUSE_PASSWORD,
        database=settings.CLICKHOUSE_DATABASE,
        secure=settings.CLICKHOUSE_SECURE,
        connect_timeout=settings.CLICKHOUSE_CONNECT_TIMEOUT,
        send_receive_timeout=settings.CLICKHOUSE_SEND_RECEIVE_TIMEOUT,
    )
