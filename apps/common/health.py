import logging
import ssl
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from urllib.request import Request, urlopen

from django.conf import settings
from django.db import DatabaseError, connection
from django.db.models import Count, Q
from django.utils import timezone
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.authentication import APIClientAuthentication
from apps.workflows.models import WorkflowAttempt

logger = logging.getLogger(__name__)

WORKER_NAMES = ("Outbox publisher", "Kafka consumer", "Workflow worker", "Analytics consumer")


def _service_result(name, healthy, detail):
    return {
        "name": name,
        "status": "healthy" if healthy else "unavailable",
        "last_checked": datetime.now(UTC),
        "detail": detail,
    }


def _postgres_probe():
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        cursor.fetchone()
    return {"ok": True, "queue_depth": None, "dead_letter_depth": None}


def _kafka_probe():
    from confluent_kafka.admin import AdminClient

    from apps.processing.adapters.kafka import _kafka_security_config

    client = AdminClient(
        {"bootstrap.servers": settings.KAFKA_BOOTSTRAP_SERVERS, **_kafka_security_config()}
    )
    client.list_topics(timeout=min(2.0, settings.BROKER_CONNECT_TIMEOUT))
    return {"ok": True}


def _rabbit_probe():
    import pika

    from apps.processing.topology import DEAD_QUEUE, TASK_QUEUE

    credentials = pika.PlainCredentials(settings.RABBITMQ_USERNAME, settings.RABBITMQ_PASSWORD)
    options = {"socket_timeout": 2}
    if settings.RABBITMQ_USE_TLS:
        context = ssl.create_default_context(cafile=settings.RABBITMQ_CA_CERT or None)
        options["ssl_options"] = pika.SSLOptions(context, settings.RABBITMQ_HOST)
    parameters = pika.ConnectionParameters(
        host=settings.RABBITMQ_HOST,
        port=settings.RABBITMQ_PORT,
        virtual_host=settings.RABBITMQ_VHOST,
        credentials=credentials,
        connection_attempts=1,
        socket_timeout=2,
        blocked_connection_timeout=2,
        **{key: value for key, value in options.items() if key != "socket_timeout"},
    )
    connection_ = pika.BlockingConnection(parameters)
    try:
        channel = connection_.channel()
        try:
            task_depth = channel.queue_declare(queue=TASK_QUEUE, passive=True).method.message_count
        except Exception:
            task_depth = None
        try:
            dead_depth = channel.queue_declare(queue=DEAD_QUEUE, passive=True).method.message_count
        except Exception:
            dead_depth = None
        return {"ok": True, "queue_depth": task_depth, "dead_letter_depth": dead_depth}
    finally:
        connection_.close()


def _clickhouse_probe():
    from apps.analytics.sink import create_clickhouse_client

    client = create_clickhouse_client()
    try:
        client.query("SELECT 1")
    finally:
        client.close()
    return {"ok": True}


def _worker_probe(name, url):
    if not settings.METRICS_TOKEN:
        return {
            "name": name,
            "status": "not_checked",
            "last_checked": None,
            "detail": "Worker metrics credential is not configured.",
        }
    try:
        request = Request(url, headers={"X-Metrics-Token": settings.METRICS_TOKEN})
        with urlopen(request, timeout=1.5) as response:
            if response.status != 200:
                raise RuntimeError("metrics endpoint returned non-success")
            body = response.read(1_000_000).decode("utf-8")
        return {
            "name": name,
            "status": "healthy",
            "last_checked": datetime.now(UTC),
            "detail": "Metrics endpoint responded.",
            "metrics": body,
        }
    except Exception:
        return {
            "name": name,
            "status": "unavailable",
            "last_checked": datetime.now(UTC),
            "detail": "Worker metrics endpoint did not respond.",
        }


def _metric_totals(texts):
    from prometheus_client.parser import text_string_to_metric_families

    wanted = {
        "eventflow_http_requests_total",
        "eventflow_http_request_duration_seconds_sum",
        "eventflow_http_request_duration_seconds_count",
        "eventflow_workflow_attempts_total",
        "eventflow_workflow_retries_total",
        "eventflow_workflow_dead_letters_total",
        "eventflow_incident_provider_calls_total",
        "eventflow_incident_provider_latency_seconds_sum",
        "eventflow_incident_provider_latency_seconds_count",
    }
    totals = {name: None for name in wanted}
    for text in texts:
        for family in text_string_to_metric_families(text):
            for sample in family.samples:
                if sample.name in wanted:
                    totals[sample.name] = (totals[sample.name] or 0.0) + float(sample.value)
    request_count = totals["eventflow_http_request_duration_seconds_count"] or 0.0
    provider_count = totals["eventflow_incident_provider_latency_seconds_count"] or 0.0
    request_sum = totals["eventflow_http_request_duration_seconds_sum"] or 0.0
    provider_sum = totals["eventflow_incident_provider_latency_seconds_sum"] or 0.0
    return {
        "api_requests_total": None
        if totals["eventflow_http_requests_total"] is None
        else int(totals["eventflow_http_requests_total"]),
        "api_average_latency_ms": (request_sum * 1000 / request_count if request_count else None),
        "worker_attempts_total": None
        if totals["eventflow_workflow_attempts_total"] is None
        else int(totals["eventflow_workflow_attempts_total"]),
        "retry_count": None
        if totals["eventflow_workflow_retries_total"] is None
        else int(totals["eventflow_workflow_retries_total"]),
        "dead_letter_count": None
        if totals["eventflow_workflow_dead_letters_total"] is None
        else int(totals["eventflow_workflow_dead_letters_total"]),
        "llm_error_count": int(
            sum(
                sample.value
                for text in texts
                for family in text_string_to_metric_families(text)
                for sample in family.samples
                if sample.name == "eventflow_incident_provider_calls_total"
                and sample.labels.get("result") == "error"
            )
        ),
        "llm_average_latency_ms": (
            provider_sum * 1000 / provider_count if provider_count else None
        ),
    }


class ServiceHealthView(APIView):
    authentication_classes = [APIClientAuthentication]
    permission_classes = [IsAuthenticated]

    @extend_schema(
        responses={
            200: inline_serializer(
                "ServiceHealthResponse",
                fields={
                    "generated_at": serializers.DateTimeField(),
                    "services": serializers.ListField(child=serializers.DictField()),
                    "metrics": serializers.DictField(),
                },
            )
        }
    )
    def get(self, request):
        generated_at = datetime.now(UTC)
        checks = {
            "PostgreSQL": _postgres_probe,
            "Kafka": _kafka_probe,
            "RabbitMQ": _rabbit_probe,
            "ClickHouse": _clickhouse_probe,
        }
        results = {}
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {executor.submit(probe): name for name, probe in checks.items()}
            for future, name in ((future, futures[future]) for future in futures):
                try:
                    results[name] = future.result(timeout=4)
                except Exception:
                    results[name] = {"ok": False, "queue_depth": None, "dead_letter_depth": None}
        services = [
            _service_result("Django API", True, "Authenticated health summary responded."),
            {
                "name": "LLM provider",
                "status": "not_checked",
                "last_checked": None,
                "detail": "The provider is not called by health checks to avoid spending quota.",
            },
            *[
                _service_result(
                    name,
                    result["ok"],
                    "Dependency probe succeeded." if result["ok"] else "Dependency probe failed.",
                )
                for name, result in results.items()
            ],
        ]
        worker_results = []
        urls = settings.WORKER_METRICS_URLS
        if settings.METRICS_TOKEN and urls:
            with ThreadPoolExecutor(max_workers=min(4, len(urls))) as executor:
                futures = [
                    executor.submit(_worker_probe, name, url)
                    for name, url in zip(WORKER_NAMES, urls, strict=False)
                ]
                worker_results = [future.result(timeout=2) for future in futures]
        else:
            worker_results = [
                {
                    "name": name,
                    "status": "not_checked",
                    "last_checked": None,
                    "detail": "Worker metrics endpoints are not configured.",
                }
                for name in WORKER_NAMES
            ]
        services.extend(
            {key: value for key, value in worker.items() if key != "metrics"}
            for worker in worker_results
        )

        metric_texts = []
        metrics_error = None
        try:
            from apps.common.metrics import metrics_payload

            metric_texts.append(metrics_payload().decode("utf-8"))
            metric_texts.extend(
                worker["metrics"] for worker in worker_results if "metrics" in worker
            )
            metrics = _metric_totals(metric_texts)
        except Exception:
            logger.warning("Health metric collection failed")
            metrics_error = "Metrics are temporarily unavailable."
            metrics = {
                "api_requests_total": None,
                "api_average_latency_ms": None,
                "worker_attempts_total": None,
                "retry_count": None,
                "dead_letter_count": None,
                "llm_error_count": None,
                "llm_average_latency_ms": None,
            }
        metrics["task_queue_depth"] = results.get("RabbitMQ", {}).get("queue_depth")
        metrics["dead_letter_queue_depth"] = results.get("RabbitMQ", {}).get("dead_letter_depth")
        metrics["availability"] = "available" if not metrics_error else "unavailable"
        if metrics_error:
            metrics["detail"] = metrics_error
        try:
            window_start = timezone.now() - timedelta(hours=24)
            workflow_metrics = WorkflowAttempt.objects.filter(
                started_at__gte=window_start
            ).aggregate(
                attempts=Count("id"),
                retries=Count("id", filter=Q(outcome=WorkflowAttempt.Outcome.RETRYING)),
                dead_letters=Count("id", filter=Q(outcome=WorkflowAttempt.Outcome.DEAD_LETTERED)),
            )
            metrics.update(
                worker_attempts_total=workflow_metrics["attempts"],
                retry_count=workflow_metrics["retries"],
                dead_letter_count=workflow_metrics["dead_letters"],
            )
        except DatabaseError:
            metrics.update(
                worker_attempts_total=None,
                retry_count=None,
                dead_letter_count=None,
            )
        return Response({"generated_at": generated_at, "services": services, "metrics": metrics})


class LivenessView(APIView):
    authentication_classes = []
    permission_classes = []

    @extend_schema(
        responses={
            200: inline_serializer("LivenessResponse", fields={"status": serializers.CharField()})
        }
    )
    def get(self, request):
        return Response({"status": "ok"}, status=status.HTTP_200_OK)


class ReadinessView(APIView):
    authentication_classes = []
    permission_classes = []

    @extend_schema(
        responses={
            200: inline_serializer(
                "ReadinessResponse",
                fields={
                    "status": serializers.CharField(),
                    "checks": serializers.DictField(child=serializers.CharField()),
                },
            ),
            503: inline_serializer(
                "ReadinessUnavailableResponse",
                fields={
                    "status": serializers.CharField(),
                    "checks": serializers.DictField(child=serializers.CharField()),
                },
            ),
        }
    )
    def get(self, request):
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        except DatabaseError:
            logger.warning("Readiness check failed: database unavailable")
            return Response(
                {"status": "not_ready", "checks": {"database": "unavailable"}},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        return Response(
            {"status": "ready", "checks": {"database": "ok"}}, status=status.HTTP_200_OK
        )
