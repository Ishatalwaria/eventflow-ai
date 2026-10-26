import logging

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.authentication import APIClientAuthentication
from apps.common.parsers import BoundedJSONParser
from apps.events.contracts import EventBatchSerializer, EventEnvelopeSerializer
from apps.events.models import Event
from apps.events.serializers import (
    EventAcceptanceSerializer,
    EventBatchResponseSerializer,
    EventDetailSerializer,
)
from apps.events.services import accept_events

logger = logging.getLogger(__name__)


def acceptance_data(result):
    return {
        "event_id": result.event.id,
        "workflow_id": result.workflow.id,
        "workflow_state": result.workflow.state,
        "duplicate": result.duplicate,
    }


class EventAPIBase(APIView):
    authentication_classes = [APIClientAuthentication]
    permission_classes = [IsAuthenticated]
    parser_classes = [BoundedJSONParser]


class EventCreateView(EventAPIBase):
    @extend_schema(
        request=EventEnvelopeSerializer,
        responses={200: EventAcceptanceSerializer, 201: EventAcceptanceSerializer},
    )
    def post(self, request):
        serializer = EventEnvelopeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = accept_events(
            client=request.user,
            envelopes=[serializer.validated_data],
            request_id=request.request_id,
        )[0]
        response_status = status.HTTP_200_OK if result.duplicate else status.HTTP_201_CREATED
        return Response(acceptance_data(result), status=response_status)


class EventBatchCreateView(EventAPIBase):
    @extend_schema(
        request=EventBatchSerializer,
        responses={200: EventBatchResponseSerializer},
    )
    def post(self, request):
        serializer = EventBatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        results = accept_events(
            client=request.user,
            envelopes=serializer.validated_data["events"],
            request_id=request.request_id,
        )
        return Response({"results": [acceptance_data(result) for result in results]})


class EventDetailView(EventAPIBase):
    @extend_schema(responses={200: EventDetailSerializer})
    def get(self, request, event_id):
        event = get_object_or_404(
            Event.objects.select_related("workflow"),
            pk=event_id,
            client=request.user,
        )
        return Response(EventDetailSerializer(event).data)
