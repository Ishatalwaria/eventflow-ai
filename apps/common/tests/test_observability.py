import json
import logging

import pytest
from config.logging import JsonFormatter
from django.test import override_settings
from rest_framework.test import APIClient

from apps.common import metrics
from apps.common.observability import bind_log_context


def test_json_logs_include_correlation_context_and_redact_credentials():
    record = logging.LogRecord(
        "eventflow.test",
        logging.INFO,
        __file__,
        1,
        "Authorization: Bearer %s api_key=%s contact=%s",
        ("token-value", "secret-value", "+1 212 555 0198"),
        None,
    )
    with bind_log_context(
        request_id="request-1",
        trace_id="request-1",
        event_id="event-1",
        workflow_id="workflow-1",
        correlation_id="correlation-1",
    ):
        output = JsonFormatter().format(record)

    parsed = json.loads(output)
    assert parsed["request_id"] == parsed["trace_id"] == "request-1"
    assert parsed["event_id"] == "event-1"
    assert parsed["workflow_id"] == "workflow-1"
    assert parsed["correlation_id"] == "correlation-1"
    assert "token-value" not in output
    assert "secret-value" not in output
    assert "+1 212 555 0198" not in output


@pytest.mark.django_db
@override_settings(METRICS_TOKEN="metrics-test-token")
def test_metrics_endpoint_requires_token_and_returns_prometheus_format():
    client = APIClient()
    denied = client.get("/metrics")
    allowed = client.get("/metrics", HTTP_X_METRICS_TOKEN="metrics-test-token")

    assert denied.status_code == 403
    assert allowed.status_code == 200
    assert "text/plain" in allowed["Content-Type"]
    assert b"eventflow_http_requests_total" in allowed.content


def test_request_context_is_returned_as_request_and_trace_headers():
    response = APIClient().get("/health/live", HTTP_X_REQUEST_ID="trace-check-123")

    assert response.status_code == 200
    assert response["X-Request-ID"] == "trace-check-123"
    assert response["X-Trace-ID"] == "trace-check-123"


def test_background_metrics_server_requires_shared_token(monkeypatch):
    captured = {}

    class FakeServer:
        def __init__(self, app):
            self.app = app

        def serve_forever(self):
            return None

    class FakeThread:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def start(self):
            return None

    def fake_make_server(_host, _port, app):
        captured["app"] = app
        return FakeServer(app)

    monkeypatch.setattr(metrics, "make_server", fake_make_server)
    monkeypatch.setattr(metrics, "Thread", FakeThread)
    with override_settings(METRICS_PORT=9100, METRICS_TOKEN="worker-metrics-token"):
        server = metrics.start_background_metrics_server()

    responses = []
    result = server.app(
        {"HTTP_X_METRICS_TOKEN": "wrong"},
        lambda status, headers: responses.append((status, headers)),
    )
    assert responses[0][0] == "403 Forbidden"
    assert b"".join(result) == b"Forbidden\n"

    responses.clear()
    result = server.app(
        {
            "HTTP_X_METRICS_TOKEN": "worker-metrics-token",
            "PATH_INFO": "/metrics",
            "REQUEST_METHOD": "GET",
            "QUERY_STRING": "",
            "SERVER_NAME": "localhost",
            "SERVER_PORT": "9100",
            "SERVER_PROTOCOL": "HTTP/1.1",
        },
        lambda status, headers: responses.append((status, headers)),
    )
    assert responses[0][0] == "200 OK"
    assert b"python_gc_objects_collected_total" in b"".join(result)
