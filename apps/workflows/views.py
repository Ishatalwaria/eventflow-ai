from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.scope import resolve_client_filter

from .models import Workflow
from .serializers import WorkflowDetailSerializer, WorkflowListQuerySerializer


class WorkflowListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = WorkflowDetailSerializer

    @extend_schema(parameters=[WorkflowListQuerySerializer])
    def get(self, request, *args, **kwargs):
        return self.list(request, *args, **kwargs)

    def get_queryset(self):
        return (
            Workflow.objects.filter(resolve_client_filter(self.request, prefix="event__client"))
            .select_related("event")
            .prefetch_related("attempts")
            .order_by("-created_at", "id")
        )

    @extend_schema(parameters=[WorkflowListQuerySerializer])
    def list(self, request, *args, **kwargs):
        query = WorkflowListQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        queryset = self.get_queryset()
        if query.validated_data.get("state"):
            queryset = queryset.filter(state=query.validated_data["state"])
        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(page, many=True)
        return self.get_paginated_response(serializer.data)


class WorkflowDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: WorkflowDetailSerializer})
    def get(self, request, workflow_id):
        workflow = get_object_or_404(
            Workflow.objects.filter(resolve_client_filter(request, prefix="event__client")).select_related("event").prefetch_related("attempts"),
            pk=workflow_id,
        )
        return Response(WorkflowDetailSerializer(workflow).data)
