from datetime import UTC, date, datetime, timedelta
from unittest.mock import Mock

import pytest
from django.contrib.auth.hashers import make_password
from django.db import connection
from rest_framework.test import APIClient as RestClient

from apps.common.models import APIClient
from apps.events.models import Event
from apps.processing.models import OutboxMessage
from apps.workflows.models import Workflow, WorkflowAttempt

pytestmark = pytest.mark.django_db


def make_client(*, analytics=False):
    secret = "analytics-test-secret"
    client = APIClient.objects.create(
        name="analytics-test",
        secret_hash=make_password(secret),
        can_view_analytics=analytics,
    )
    return client, f"{client.pk}.{secret}"


def sample_report(latest=None):
    latest = latest or datetime.now(UTC) - timedelta(seconds=20)
    return {
        "processed_per_minute": [(latest.replace(second=0, microsecond=0), 3)],
        "success_count": 2,
        "failure_count": 1,
        "success_rate": 2 / 3,
        "failure_rate": 1 / 3,
        "latency_ms_p50_p95_p99": [12.0, 30.0, 45.0],
        "retry_count_distribution": [(1, 2)],
        "frequent_error_codes": [("INSUFFICIENT_INVENTORY", 1)],
        "failure_rate_by_stage": [
            {"stage": "order_validation", "failures": 1, "terminal_count": 3, "failure_rate": 1 / 3}
        ],
        "oldest_event_time": latest - timedelta(minutes=2),
        "latest_event_time": latest,
    }


def test_lifecycle_analytics_requires_explicit_capability(monkeypatch):
    report = Mock(return_value=sample_report())
    monkeypatch.setattr("apps.analytics.views.lifecycle_report", report)
    _, regular_token = make_client()
    client = RestClient()

    unauthenticated = client.get(
        "/api/v1/analytics/lifecycle?date_from=2026-10-01&date_to=2026-10-30"
    )
    forbidden = client.get(
        "/api/v1/analytics/lifecycle?date_from=2026-10-01&date_to=2026-10-30",
        HTTP_AUTHORIZATION=f"Bearer {regular_token}",
    )

    assert unauthenticated.status_code == 401
    assert forbidden.status_code == 403
    assert report.call_count == 0


def test_tenant_lifecycle_analytics_is_available_and_scoped_to_client():
    owner, token = make_client()
    other, _ = make_client()
    now = datetime.now(UTC)

    def create_workflow(client, *, state, suffix):
        event = Event.objects.create(
            client=client,
            event_type="order.created",
            schema_version=1,
            source="test",
            idempotency_key=f"key-{suffix}",
            occurred_at=now,
            correlation_id=f"corr-{suffix}",
            request_id=f"request-{suffix}",
            payload={},
        )
        return Workflow.objects.create(
            event=event,
            state=state,
            current_stage="order_validation",
            started_at=now - timedelta(milliseconds=42),
            finished_at=now,
        )

    succeeded = create_workflow(owner, state=Workflow.State.SUCCEEDED, suffix="owner")
    WorkflowAttempt.objects.create(
        workflow=succeeded,
        stage="order_validation",
        attempt_number=1,
        outcome=WorkflowAttempt.Outcome.SUCCEEDED,
        started_at=now - timedelta(milliseconds=42),
        finished_at=now,
        duration_ms=42,
    )
    create_workflow(other, state=Workflow.State.FAILED, suffix="other")

    response = RestClient().get(
        f"/api/v1/analytics/tenant-lifecycle?date_from={now.date()}&date_to={now.date()}",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )

    assert response.status_code == 200
    assert response.data["source"] == "postgresql"
    assert response.data["consistency"] == "current_state"
    assert response.data["success_count"] == 1
    assert response.data["failure_count"] == 0
    assert response.data["processed_per_minute"][0]["count"] == 1
    if connection.vendor == "postgresql":
        assert response.data["latency_ms"]["p50"] == pytest.approx(42)


def test_overview_returns_tenant_scoped_summary_and_recent_records():
    owner, token = make_client()
    other, _ = make_client()
    now = datetime.now(UTC)

    def create_event(client, suffix):
        return Event.objects.create(
            client=client,
            event_type="order.created",
            schema_version=1,
            source="test",
            idempotency_key=f"overview-key-{suffix}",
            occurred_at=now,
            correlation_id=f"overview-corr-{suffix}",
            request_id=f"overview-request-{suffix}",
            payload={},
        )

    event = create_event(owner, "owner")
    workflow = Workflow.objects.create(
        event=event,
        state=Workflow.State.SUCCEEDED,
        started_at=now - timedelta(milliseconds=20),
        finished_at=now,
    )
    OutboxMessage.objects.create(
        event=event,
        topic="eventflow.domain.events.v1",
        payload={"event_id": str(event.pk)},
    )
    other_event = create_event(other, "other")
    Workflow.objects.create(event=other_event, state=Workflow.State.FAILED)

    response = RestClient().get(
        "/api/v1/analytics/overview",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )

    assert response.status_code == 200
    assert response.data["event_count"] == 1
    assert response.data["processed_event_count"] == 1
    assert response.data["workflow_state_counts"][Workflow.State.SUCCEEDED] == 1
    assert response.data["workflow_state_counts"][Workflow.State.FAILED] == 0
    assert response.data["recent_events"][0]["id"] == str(event.pk)
    assert response.data["recent_workflows"][0]["id"] == str(workflow.pk)
    assert response.data["outbox_pending_count"] == 1
    if connection.vendor == "postgresql":
        assert response.data["average_processing_latency_ms"] == pytest.approx(20)


def test_lifecycle_analytics_returns_bounded_report_and_freshness(monkeypatch):
    latest = datetime.now(UTC) - timedelta(seconds=20)
    report = Mock(return_value=sample_report(latest))
    monkeypatch.setattr("apps.analytics.views.lifecycle_report", report)
    _client, token = make_client(analytics=True)

    response = RestClient().get(
        "/api/v1/analytics/lifecycle?date_from=2026-10-01&date_to=2026-10-30",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )

    assert response.status_code == 200
    assert response.data["source"] == "clickhouse"
    assert response.data["consistency"] == "eventually_consistent"
    assert response.data["date_from"] == "2026-10-01"
    assert response.data["date_to"] == "2026-10-30"
    assert response.data["data_lag_seconds"] is not None
    assert response.data["latency_ms"] == {"p50": 12.0, "p95": 30.0, "p99": 45.0}
    assert response.data["retry_count_distribution"] == [{"retry_count": 1, "workflow_count": 2}]
    assert response.data["frequent_error_codes"][0]["error_code"] == "INSUFFICIENT_INVENTORY"
    assert response.data["processed_per_minute"][0]["count"] == 3
    report.assert_called_once_with(date(2026, 10, 1), date(2026, 10, 30))


@pytest.mark.parametrize(
    ("date_from", "date_to"),
    [("2026-10-31", "2026-10-01"), ("2025-01-01", "2026-01-04")],
)
def test_lifecycle_analytics_rejects_invalid_or_oversized_range(date_from, date_to):
    _client, token = make_client(analytics=True)
    response = RestClient().get(
        f"/api/v1/analytics/lifecycle?date_from={date_from}&date_to={date_to}",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )
    assert response.status_code == 400


def test_lifecycle_analytics_returns_safe_unavailable_error(monkeypatch):
    def fail(*_args, **_kwargs):
        raise RuntimeError("private ClickHouse endpoint")

    monkeypatch.setattr("apps.analytics.views.lifecycle_report", fail)
    _client, token = make_client(analytics=True)
    response = RestClient().get(
        "/api/v1/analytics/lifecycle?date_from=2026-10-01&date_to=2026-10-30",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )
    assert response.status_code == 503
    assert response.data["error"]["code"] == "ANALYTICS_UNAVAILABLE"
    assert "private ClickHouse endpoint" not in str(response.data)
