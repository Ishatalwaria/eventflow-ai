import logging
import uuid

from django.db.models import Q
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.pagination import BoundedPageNumberPagination
from apps.common.parsers import BoundedJSONParser
from apps.common.scope import get_effective_client, resolve_client_filter
from apps.events.contracts import EventBatchSerializer, EventEnvelopeSerializer
from apps.events.models import Event
from apps.events.serializers import (
    EventAcceptanceSerializer,
    EventBatchResponseSerializer,
    EventDetailSerializer,
    EventListQuerySerializer,
    EventListSerializer,
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
    permission_classes = [IsAuthenticated]
    parser_classes = [BoundedJSONParser]


class EventBatchCreateView(EventAPIBase):
    @extend_schema(
        request=EventBatchSerializer,
        responses={200: EventBatchResponseSerializer},
    )
    def post(self, request):
        serializer = EventBatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        client = get_effective_client(request)
        if client is None:
            return Response(
                {
                    "error": {
                        "code": "UNAUTHORIZED",
                        "message": "Valid client credentials required.",
                    }
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )
        results = accept_events(
            client=client,
            envelopes=serializer.validated_data["events"],
            request_id=request.request_id,
        )
        return Response({"results": [acceptance_data(result) for result in results]})


class EventCollectionView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [BoundedJSONParser]
    serializer_class = EventListSerializer
    pagination_class = BoundedPageNumberPagination

    @extend_schema(
        request=EventEnvelopeSerializer,
        responses={200: EventAcceptanceSerializer, 201: EventAcceptanceSerializer},
    )
    def post(self, request):
        serializer = EventEnvelopeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        client = get_effective_client(request)
        if client is None:
            return Response(
                {
                    "error": {
                        "code": "UNAUTHORIZED",
                        "message": "Valid client credentials required.",
                    }
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )
        result = accept_events(
            client=client,
            envelopes=[serializer.validated_data],
            request_id=request.request_id,
        )[0]
        response_status = status.HTTP_200_OK if result.duplicate else status.HTTP_201_CREATED
        return Response(acceptance_data(result), status=response_status)

    def get_queryset(self):
        return (
            Event.objects.filter(resolve_client_filter(self.request, prefix="client"))
            .select_related("workflow")
            .order_by("-received_at", "-id")
        )

    @extend_schema(parameters=[EventListQuerySerializer])
    def get(self, request, *args, **kwargs):
        return self.list(request, *args, **kwargs)

    def list(self, request, *args, **kwargs):
        query = EventListQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        params = query.validated_data
        queryset = self.get_queryset()
        if params.get("event_type"):
            queryset = queryset.filter(event_type=params["event_type"])
        if params.get("date_from"):
            queryset = queryset.filter(received_at__date__gte=params["date_from"])
        if params.get("date_to"):
            queryset = queryset.filter(received_at__date__lte=params["date_to"])
        search = params.get("search", "")
        if search:
            search_filter = (
                Q(event_type__icontains=search)
                | Q(source__icontains=search)
                | Q(idempotency_key__icontains=search)
                | Q(correlation_id__icontains=search)
            )
            try:
                search_filter |= Q(pk=uuid.UUID(search))
            except ValueError:
                pass
            queryset = queryset.filter(search_filter)
        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(page, many=True)
        return self.get_paginated_response(serializer.data)


class EventDetailView(EventAPIBase):
    @extend_schema(responses={200: EventDetailSerializer})
    def get(self, request, event_id):
        event = get_object_or_404(
            Event.objects.filter(resolve_client_filter(request, prefix="client")).select_related(
                "workflow"
            ),
            pk=event_id,
        )
        return Response(EventDetailSerializer(event).data)
