"""Prometheus exposition for the API and background management commands."""

from threading import Thread
from wsgiref.simple_server import make_server

from django.conf import settings
from django.http import HttpResponse
from drf_spectacular.utils import extend_schema
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    generate_latest,
    make_wsgi_app,
    multiprocess,
)
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from .observability import HTTP_REQUESTS


def metrics_payload():
    if settings.PROMETHEUS_MULTIPROC_DIR:
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
    else:
        from prometheus_client import REGISTRY

        registry = REGISTRY
    return generate_latest(registry)


class MetricsView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = []

    @extend_schema(exclude=True)
    def get(self, request):
        expected = settings.METRICS_TOKEN
        supplied = request.headers.get("X-Metrics-Token", "")
        if not expected or not _constant_time_equal(supplied, expected):
            return HttpResponse("Forbidden\n", status=403, content_type="text/plain")
        HTTP_REQUESTS.labels(method="GET", route="/metrics", status="200").inc()
        return HttpResponse(metrics_payload(), content_type=CONTENT_TYPE_LATEST)


def _constant_time_equal(supplied, expected):
    import secrets

    return secrets.compare_digest(supplied.encode("utf-8"), expected.encode("utf-8"))


def start_background_metrics_server():
    """Expose this single-purpose worker's process-local metrics when enabled."""
    port = settings.METRICS_PORT
    token = settings.METRICS_TOKEN
    if not port or not token:
        return None
    exposition_app = make_wsgi_app()

    def authenticated_app(environ, start_response):
        supplied = environ.get("HTTP_X_METRICS_TOKEN", "")
        if not _constant_time_equal(supplied, token):
            start_response(
                "403 Forbidden",
                [("Content-Type", "text/plain; charset=utf-8"), ("Content-Length", "10")],
            )
            return [b"Forbidden\n"]
        return exposition_app(environ, start_response)

    server = make_server("0.0.0.0", port, authenticated_app)
    Thread(target=server.serve_forever, name="eventflow-metrics", daemon=True).start()
    return server
