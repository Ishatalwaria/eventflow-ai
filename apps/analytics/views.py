import logging
from datetime import UTC, datetime, time, timedelta

from django.db import connection
from django.db.models import Count, Max, Min, Q
from django.db.models.functions import TruncMinute
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.scope import resolve_client_filter
from apps.events.models import Event
from apps.processing.models import OutboxMessage
from apps.workflows.models import Workflow, WorkflowAttempt

from .permissions import CanViewAnalytics
from .queries import lifecycle_report
from .serializers import (
    LifecycleAnalyticsQuerySerializer,
    LifecycleAnalyticsSerializer,
    OverviewSerializer,
)

logger = logging.getLogger(__name__)


class AnalyticsUnavailable(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "Analytics data is temporarily unavailable."
    default_code = "ANALYTICS_UNAVAILABLE"


class LifecycleAnalyticsView(APIView):
    permission_classes = [IsAuthenticated, CanViewAnalytics]

    @extend_schema(
        description=(
            "Global ClickHouse lifecycle analytics. Requires an API client created with "
            "--analytics-access. Regular clients should use /api/v1/analytics/tenant-lifecycle."
        ),
        parameters=[LifecycleAnalyticsQuerySerializer],
        responses={200: LifecycleAnalyticsSerializer},
    )
    def get(self, request):
        query = LifecycleAnalyticsQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        date_from = query.validated_data["date_from"]
        date_to = query.validated_data["date_to"]
        try:
            report = lifecycle_report(date_from, date_to)
        except Exception as exc:
            logger.warning("Analytics query failed error_type=%s", type(exc).__name__)
            raise AnalyticsUnavailable() from None

        generated_at = timezone.now()
        latest = report["latest_event_time"]
        if latest is not None and timezone.is_naive(latest):
            latest = timezone.make_aware(latest, UTC)
        data_lag_seconds = (
            None if latest is None else max(0, int((generated_at - latest).total_seconds()))
        )
        terminal_count = report["success_count"] + report["failure_count"]
        quantiles = report["latency_ms_p50_p95_p99"]
        latency = (
            {"p50": None, "p95": None, "p99": None}
            if not terminal_count or quantiles is None
            else {"p50": quantiles[0], "p95": quantiles[1], "p99": quantiles[2]}
        )
        payload = {
            "date_from": date_from,
            "date_to": date_to,
            "source": "clickhouse",
            "consistency": "eventually_consistent",
            "generated_at": generated_at,
            "data_lag_seconds": data_lag_seconds,
            "oldest_event_time": report["oldest_event_time"],
            "latest_event_time": latest,
            "processed_per_minute": [
                {"minute": minute, "count": count}
                for minute, count in report["processed_per_minute"]
            ],
            "success_count": report["success_count"],
            "failure_count": report["failure_count"],
            "success_rate": report["success_rate"],
            "failure_rate": report["failure_rate"],
            "latency_ms": latency,
            "retry_count_distribution": [
                {"retry_count": retries, "workflow_count": count}
                for retries, count in report["retry_count_distribution"]
            ],
            "frequent_error_codes": [
                {"error_code": error_code, "count": count}
                for error_code, count in report["frequent_error_codes"]
            ],
            "failure_rate_by_stage": report["failure_rate_by_stage"],
        }
        return Response(LifecycleAnalyticsSerializer(payload).data)


class TenantLifecycleAnalyticsView(APIView):
    """Current-state analytics, scoped to the authenticated API client or user workspace."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        parameters=[LifecycleAnalyticsQuerySerializer],
        responses={200: LifecycleAnalyticsSerializer},
    )
    def get(self, request):
        query = LifecycleAnalyticsQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        date_from = query.validated_data["date_from"]
        date_to = query.validated_data["date_to"]
        tz = timezone.get_current_timezone()
        start = timezone.make_aware(datetime.combine(date_from, time.min), tz)
        end = timezone.make_aware(datetime.combine(date_to + timedelta(days=1), time.min), tz)

        client_filter = resolve_client_filter(request, prefix="client")
        events = Event.objects.filter(client_filter, received_at__gte=start, received_at__lt=end)
        workflows = Workflow.objects.filter(resolve_client_filter(request, prefix="event__client"))
        terminal = workflows.filter(
            state__in=(
                Workflow.State.SUCCEEDED,
                Workflow.State.FAILED,
                Workflow.State.DEAD_LETTERED,
            ),
            finished_at__gte=start,
            finished_at__lt=end,
        )
        success_count = terminal.filter(state=Workflow.State.SUCCEEDED).count()
        failure_count = terminal.filter(
            state__in=(Workflow.State.FAILED, Workflow.State.DEAD_LETTERED)
        ).count()
        terminal_count = success_count + failure_count
        retries = (
            WorkflowAttempt.objects.filter(
                resolve_client_filter(request, prefix="workflow__event__client"),
                started_at__gte=start,
                started_at__lt=end,
                outcome=WorkflowAttempt.Outcome.RETRYING,
            )
            .values("workflow_id")
            .annotate(retry_count=Count("id"))
            .values("retry_count")
            .annotate(workflow_count=Count("workflow_id"))
            .order_by("retry_count")
        )
        errors = (
            WorkflowAttempt.objects.filter(
                resolve_client_filter(request, prefix="workflow__event__client"),
                started_at__gte=start,
                started_at__lt=end,
                outcome__in=(WorkflowAttempt.Outcome.FAILED, WorkflowAttempt.Outcome.DEAD_LETTERED),
            )
            .exclude(error_code="")
            .values("error_code")
            .annotate(count=Count("id"))
            .order_by("-count", "error_code")[:20]
        )
        stage_totals = (
            WorkflowAttempt.objects.filter(
                resolve_client_filter(request, prefix="workflow__event__client"),
                started_at__gte=start,
                started_at__lt=end,
                outcome__in=(
                    WorkflowAttempt.Outcome.SUCCEEDED,
                    WorkflowAttempt.Outcome.FAILED,
                    WorkflowAttempt.Outcome.DEAD_LETTERED,
                ),
            )
            .values("stage")
            .annotate(
                failures=Count(
                    "id",
                    filter=Q(
                        outcome__in=(
                            WorkflowAttempt.Outcome.FAILED,
                            WorkflowAttempt.Outcome.DEAD_LETTERED,
                        )
                    ),
                ),
                terminal_count=Count("id"),
            )
            .order_by("stage")
        )
        latest = events.aggregate(latest=Max("received_at"))["latest"]
        percentiles = None
        matching_client_ids = list(
            Event.objects.filter(client_filter).values_list("client_id", flat=True).distinct()
        )
        if connection.vendor == "postgresql" and matching_client_ids:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT percentile_cont(ARRAY[0.50, 0.95, 0.99])
                       WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM
                           (workflows_workflow.finished_at -
                           workflows_workflow.started_at)) * 1000)
                       FROM workflows_workflow
                       JOIN events_event ON events_event.id = workflows_workflow.event_id
                       WHERE events_event.client_id = ANY(%s::uuid[])
                         AND workflows_workflow.state IN (%s, %s, %s)
                         AND workflows_workflow.finished_at >= %s
                         AND workflows_workflow.finished_at < %s
                         AND workflows_workflow.started_at IS NOT NULL
                         AND workflows_workflow.finished_at IS NOT NULL""",
                    [
                        matching_client_ids,
                        Workflow.State.SUCCEEDED,
                        Workflow.State.FAILED,
                        Workflow.State.DEAD_LETTERED,
                        start,
                        end,
                    ],
                )
                res = cursor.fetchone()
                if res:
                    percentiles = res[0]
        payload = {
            "date_from": date_from,
            "date_to": date_to,
            "source": "postgresql",
            "consistency": "current_state",
            "generated_at": timezone.now(),
            "data_lag_seconds": None
            if latest is None
            else max(0, int((timezone.now() - latest).total_seconds())),
            "oldest_event_time": events.aggregate(oldest=Min("received_at"))["oldest"],
            "latest_event_time": latest,
            "processed_per_minute": [
                {"minute": row["minute"], "count": row["count"]}
                for row in terminal.annotate(minute=TruncMinute("finished_at"))
                .values("minute")
                .annotate(count=Count("id"))
                .order_by("minute")
            ],
            "success_count": success_count,
            "failure_count": failure_count,
            "success_rate": success_count / terminal_count if terminal_count else 0.0,
            "failure_rate": failure_count / terminal_count if terminal_count else 0.0,
            "latency_ms": {"p50": percentiles[0], "p95": percentiles[1], "p99": percentiles[2]}
            if percentiles and terminal_count
            else {"p50": None, "p95": None, "p99": None},
            "retry_count_distribution": list(retries),
            "frequent_error_codes": list(errors),
            "failure_rate_by_stage": [
                {
                    "stage": row["stage"],
                    "failures": row["failures"],
                    "terminal_count": row["terminal_count"],
                    "failure_rate": row["failures"] / row["terminal_count"]
                    if row["terminal_count"]
                    else 0.0,
                }
                for row in stage_totals
            ],
        }
        return Response(LifecycleAnalyticsSerializer(payload).data)


class OverviewView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: OverviewSerializer})
    def get(self, request):
        client_filter = resolve_client_filter(request, prefix="client")
        wf_filter = resolve_client_filter(request, prefix="event__client")
        events = Event.objects.filter(client_filter)
        workflows = Workflow.objects.filter(wf_filter)
        state_counts = {state: 0 for state, _label in Workflow.State.choices}
        state_counts.update(
            {
                row["state"]: row["count"]
                for row in workflows.values("state").annotate(count=Count("id"))
            }
        )
        terminal_workflows = workflows.filter(
            state__in=(
                Workflow.State.SUCCEEDED,
                Workflow.State.FAILED,
                Workflow.State.DEAD_LETTERED,
            ),
            finished_at__isnull=False,
        )
        generated_at = timezone.now()
        series_start = generated_at - timedelta(days=7)
        activity = (
            terminal_workflows.filter(finished_at__gte=series_start)
            .annotate(minute=TruncMinute("finished_at"))
            .values("minute")
            .annotate(count=Count("id"))
            .order_by("minute")
        )
        average_latency = None
        matching_client_ids = list(events.values_list("client_id", flat=True).distinct())
        if connection.vendor == "postgresql" and matching_client_ids:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT AVG(EXTRACT(EPOCH FROM
                       (workflows_workflow.finished_at - workflows_workflow.started_at)) * 1000)
                       FROM workflows_workflow
                       JOIN events_event ON events_event.id = workflows_workflow.event_id
                       WHERE events_event.client_id = ANY(%s::uuid[])
                         AND workflows_workflow.state IN (%s, %s, %s)
                         AND workflows_workflow.started_at IS NOT NULL
                         AND workflows_workflow.finished_at IS NOT NULL""",
                    [
                        matching_client_ids,
                        Workflow.State.SUCCEEDED,
                        Workflow.State.FAILED,
                        Workflow.State.DEAD_LETTERED,
                    ],
                )
                res = cursor.fetchone()
                if res:
                    average_latency = res[0]
        recent_events = [
            {
                "id": event.id,
                "event_type": event.event_type,
                "source": event.source,
                "schema_version": event.schema_version,
                "idempotency_key": event.idempotency_key,
                "correlation_id": event.correlation_id,
                "received_at": event.received_at,
                "workflow_id": getattr(event, "workflow", None).id
                if hasattr(event, "workflow")
                else None,
                "workflow_state": getattr(event, "workflow", None).state
                if hasattr(event, "workflow")
                else None,
            }
            for event in events.select_related("workflow").order_by("-received_at", "-id")[:6]
        ]
        recent_workflows = (
            workflows.select_related("event")
            .annotate(attempt_count=Count("attempts"))
            .order_by("-created_at", "id")[:6]
        )
        outbox = OutboxMessage.objects.filter(wf_filter)
        payload = {
            "generated_at": generated_at,
            "event_count": events.count(),
            "processed_event_count": terminal_workflows.count(),
            "workflow_state_counts": state_counts,
            "average_processing_latency_ms": average_latency,
            "processed_per_minute": list(activity),
            "recent_events": recent_events,
            "recent_workflows": [
                {
                    "id": workflow.id,
                    "event_id": workflow.event_id,
                    "state": workflow.state,
                    "current_stage": workflow.current_stage,
                    "created_at": workflow.created_at,
                    "updated_at": workflow.updated_at,
                    "started_at": workflow.started_at,
                    "finished_at": workflow.finished_at,
                    "attempt_count": workflow.attempt_count,
                }
                for workflow in recent_workflows
            ],
            "outbox_pending_count": outbox.filter(
                published_at__isnull=True, dead_lettered_at__isnull=True
            ).count(),
            "outbox_dead_lettered_count": outbox.filter(dead_lettered_at__isnull=False).count(),
        }
        return Response(OverviewSerializer(payload).data)
