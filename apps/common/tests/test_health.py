import json
import uuid
from unittest.mock import patch

import pytest
from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.db import OperationalError
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.common.models import APIClient as APIClientModel
from apps.events.models import Event
from apps.workflows.models import Workflow, WorkflowAttempt


def test_root_redirects_to_api_documentation():
    response = APIClient().get("/")

    assert response.status_code == 302
    assert response["Location"] == "/api/docs/"


def test_liveness_does_not_check_database():
    with patch("apps.common.health.connection.cursor", side_effect=OperationalError):
        response = APIClient().get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_reports_database_available():
    with patch("apps.common.health.connection.cursor") as cursor_factory:
        response = APIClient().get("/health/ready")

    cursor_factory.return_value.__enter__.return_value.execute.assert_called_once_with("SELECT 1")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "checks": {"database": "ok"}}


def test_readiness_returns_safe_unavailable_response():
    with patch("apps.common.health.connection.cursor", side_effect=OperationalError):
        response = APIClient().get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "checks": {"database": "unavailable"},
    }


def test_drf_defaults_deny_anonymous_access_and_public_health_exceptions_remain_public():
    assert settings.REST_FRAMEWORK["DEFAULT_PERMISSION_CLASSES"] == [
        "rest_framework.permissions.IsAuthenticated"
    ]
    assert settings.REST_FRAMEWORK["DEFAULT_AUTHENTICATION_CLASSES"] == [
        "apps.common.authentication.APIClientAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ]

    client = APIClient()
    assert client.get("/api/v1/events").status_code == 401
    assert client.get("/health/services").status_code == 401
    assert client.get("/health/live").status_code == 200
    with patch("apps.common.health.connection.cursor"):
        assert client.get("/health/ready").status_code == 200
    assert client.get("/metrics").status_code == 403


def test_openapi_schema_endpoint_is_available():
    response = APIClient().get("/api/schema/", HTTP_ACCEPT="application/vnd.oai.openapi+json")

    assert response.status_code == 200
    schema = json.loads(response.content)
    assert "/health/live" in schema["paths"]
    assert "/health/ready" in schema["paths"]
    assert "/api/v1/events" in schema["paths"]
    assert "/api/v1/events/batch" in schema["paths"]
    assert "/api/v1/events/{event_id}" in schema["paths"]
    assert "/api/v1/workflows" in schema["paths"]
    assert "/api/v1/workflows/{workflow_id}" in schema["paths"]
    assert "APIErrorEnvelope" in schema["components"]["schemas"]
    assert "default" in schema["paths"]["/api/v1/events"]["get"]["responses"]
    workflow_parameters = schema["paths"]["/api/v1/workflows"]["get"]["parameters"]
    assert "state" in {parameter["name"] for parameter in workflow_parameters}
    assert "ClientBearer" in schema["components"]["securitySchemes"]


@pytest.mark.django_db
@override_settings(WORKER_METRICS_URLS=[], METRICS_TOKEN="health-test-private-token")
def test_service_health_summary_requires_api_client_and_returns_allowlisted_metrics(monkeypatch):
    client_record = APIClientModel.objects.create(
        name="health-dashboard",
        secret_hash=make_password("health-test-secret"),
    )
    token = f"{client_record.pk}.health-test-secret"
    event = Event.objects.create(
        client=client_record,
        event_type="order.created",
        schema_version=1,
        source="health-test",
        idempotency_key=str(uuid.uuid4()),
        occurred_at=timezone.now(),
        correlation_id="health-test-correlation",
        request_id="health-test-request",
        payload={},
    )
    workflow = Workflow.objects.create(event=event)
    started_at = timezone.now()
    for attempt_number, outcome in enumerate(
        (
            WorkflowAttempt.Outcome.SUCCEEDED,
            WorkflowAttempt.Outcome.RETRYING,
            WorkflowAttempt.Outcome.DEAD_LETTERED,
        ),
        start=1,
    ):
        WorkflowAttempt.objects.create(
            workflow=workflow,
            stage="order_validation",
            attempt_number=attempt_number,
            outcome=outcome,
            started_at=started_at,
            finished_at=started_at,
        )
    for name in ("_postgres_probe", "_kafka_probe", "_rabbit_probe", "_clickhouse_probe"):
        monkeypatch.setattr(
            "apps.common.health." + name,
            lambda: {"ok": True, "queue_depth": 4, "dead_letter_depth": 1},
        )
    monkeypatch.setattr(
        "apps.common.metrics.metrics_payload",
        lambda: (
            b"# HELP eventflow_http_requests_total requests\n"
            b'eventflow_http_requests_total{method="GET",route="health/services",status="200"} 7\n'
        ),
    )

    unauthenticated = APIClient().get("/health/services")
    response = APIClient().get(
        "/health/services",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )

    assert unauthenticated.status_code == 401
    assert response.status_code == 200
    assert {service["name"] for service in response.data["services"]} >= {
        "Django API",
        "PostgreSQL",
        "Kafka",
        "RabbitMQ",
        "ClickHouse",
        "LLM provider",
    }
    assert response.data["metrics"]["api_requests_total"] == 7
    assert response.data["metrics"]["worker_attempts_total"] == 3
    assert response.data["metrics"]["retry_count"] == 1
    assert response.data["metrics"]["dead_letter_count"] == 1
    assert response.data["metrics"]["llm_error_count"] == 0
    assert response.data["metrics"]["llm_average_latency_ms"] is None
    assert response.data["metrics"]["task_queue_depth"] == 4
    assert response.data["metrics"]["dead_letter_queue_depth"] == 1
    assert "health-test-private-token" not in str(response.data)
