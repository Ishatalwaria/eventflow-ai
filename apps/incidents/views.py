import uuid

from django.db.models import Q
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.exceptions import APIException
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.scope import get_effective_client, resolve_client_filter
from apps.incidents.models import IncidentSummary
from apps.workflows.models import Workflow

from .providers.base import PermanentProviderError, TransientProviderError
from .serializers import (
    IncidentSummaryListQuerySerializer,
    IncidentSummaryListSerializer,
    IncidentSummarySerializer,
)
from .service import create_incident_summary
from .throttles import IncidentSummaryThrottle


class IncidentSummaryUnavailable(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "Incident analysis is temporarily unavailable."
    default_code = "INCIDENT_ANALYSIS_UNAVAILABLE"

    def __init__(self, error_code="INCIDENT_ANALYSIS_UNAVAILABLE"):
        self.default_code = error_code
        super().__init__(self.default_detail, code=error_code.lower())


class IncidentSummaryInvalid(APIException):
    status_code = status.HTTP_502_BAD_GATEWAY
    default_detail = "Incident analysis could not produce a valid response."
    default_code = "INCIDENT_ANALYSIS_INVALID"

    def __init__(self, error_code="INCIDENT_ANALYSIS_INVALID"):
        self.default_code = error_code
        detail = self.default_detail
        if error_code == "OPENAI_QUOTA_EXHAUSTED":
            detail = "The configured incident provider has no available API quota."
        elif error_code == "OPENAI_AUTH_REJECTED":
            detail = "The configured incident provider rejected its credentials."
        elif error_code == "OPENAI_API_KEY_MISSING":
            detail = "The incident provider API key is not configured for this API process."
        elif error_code == "GEMINI_QUOTA_EXHAUSTED":
            detail = "The configured Gemini project has no available API credits."
        elif error_code == "GEMINI_AUTH_REJECTED":
            detail = "Gemini rejected its API key or project access."
        elif error_code == "GEMINI_API_KEY_MISSING":
            detail = "GEMINI_API_KEY is not configured for this API process."
        elif error_code == "GEMINI_INVALID_REQUEST":
            detail = "Gemini rejected the generation request or structured-output schema."
        elif error_code == "GEMINI_MODEL_NOT_FOUND":
            detail = "The configured Gemini model is unavailable to this API key."
        super().__init__(detail, code=error_code.lower())


class WorkflowNotFailed(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "Incident summaries are available only for failed workflows."
    default_code = "WORKFLOW_NOT_FAILED"


class IncidentSummaryCreateView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [IncidentSummaryThrottle]

    @extend_schema(request=None, responses={201: IncidentSummarySerializer})
    def post(self, request, workflow_id):
        workflow = get_object_or_404(
            Workflow.objects.filter(
                resolve_client_filter(request, prefix="event__client")
            ).select_related("event"),
            pk=workflow_id,
        )
        if workflow.state not in {Workflow.State.FAILED, Workflow.State.DEAD_LETTERED}:
            raise WorkflowNotFailed()
        client = get_effective_client(request)
        try:
            record = create_incident_summary(workflow, client)
        except TransientProviderError as exc:
            raise IncidentSummaryUnavailable(exc.error_code) from None
        except PermanentProviderError as exc:
            raise IncidentSummaryInvalid(exc.error_code) from None
        return Response(IncidentSummarySerializer(record).data, status=status.HTTP_201_CREATED)


class IncidentSummaryListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = IncidentSummaryListSerializer

    def get_queryset(self):
        return (
            IncidentSummary.objects.filter(
                resolve_client_filter(self.request, prefix="workflow__event__client")
            )
            .select_related("workflow", "workflow__event")
            .order_by("-created_at", "-id")
        )

    @extend_schema(parameters=[IncidentSummaryListQuerySerializer])
    def get(self, request, *args, **kwargs):
        query = IncidentSummaryListQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        params = query.validated_data
        queryset = self.get_queryset()
        if params.get("workflow_state"):
            queryset = queryset.filter(workflow__state=params["workflow_state"])
        search = params.get("search", "")
        if search:
            search_filter = (
                Q(summary__headline__icontains=search)
                | Q(provider__icontains=search)
                | Q(model__icontains=search)
            )
            try:
                search_id = uuid.UUID(search)
            except ValueError:
                pass
            else:
                search_filter |= (
                    Q(pk=search_id) | Q(workflow_id=search_id) | Q(workflow__event_id=search_id)
                )
            queryset = queryset.filter(search_filter)
        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(page, many=True)
        return self.get_paginated_response(serializer.data)


class IncidentSummaryDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: IncidentSummarySerializer})
    def get(self, request, incident_id):
        summary = get_object_or_404(
            IncidentSummary.objects.filter(
                resolve_client_filter(request, prefix="workflow__event__client")
            ).select_related("workflow", "workflow__event"),
            pk=incident_id,
        )
        return Response(IncidentSummarySerializer(summary).data)
