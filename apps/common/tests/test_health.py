import json
from unittest.mock import patch

from django.db import OperationalError
from rest_framework.test import APIClient


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


def test_openapi_schema_endpoint_is_available():
    response = APIClient().get("/api/schema/", HTTP_ACCEPT="application/vnd.oai.openapi+json")

    assert response.status_code == 200
    schema = json.loads(response.content)
    assert "/health/live" in schema["paths"]
    assert "/health/ready" in schema["paths"]
