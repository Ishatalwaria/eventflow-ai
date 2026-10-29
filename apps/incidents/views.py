from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.authentication import APIClientAuthentication
from apps.workflows.models import Workflow

from .providers.base import PermanentProviderError, TransientProviderError
from .serializers import IncidentSummarySerializer
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
    authentication_classes = [APIClientAuthentication]
    permission_classes = [IsAuthenticated]
    throttle_classes = [IncidentSummaryThrottle]

    @extend_schema(request=None, responses={201: IncidentSummarySerializer})
    def post(self, request, workflow_id):
        workflow = get_object_or_404(
            Workflow.objects.select_related("event"),
            pk=workflow_id,
            event__client=request.user,
        )
        if workflow.state not in {Workflow.State.FAILED, Workflow.State.DEAD_LETTERED}:
            raise WorkflowNotFailed()
        try:
            record = create_incident_summary(workflow, request.user)
        except TransientProviderError as exc:
            raise IncidentSummaryUnavailable(exc.error_code) from None
        except PermanentProviderError as exc:
            raise IncidentSummaryInvalid(exc.error_code) from None
        return Response(IncidentSummarySerializer(record).data, status=status.HTTP_201_CREATED)
