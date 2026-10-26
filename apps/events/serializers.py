from rest_framework import serializers

from apps.events.models import Event
from apps.workflows.models import Workflow


class WorkflowSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Workflow
        fields = ("id", "state", "current_stage", "created_at", "updated_at")


class EventAcceptanceSerializer(serializers.Serializer):
    event_id = serializers.UUIDField()
    workflow_id = serializers.UUIDField()
    workflow_state = serializers.CharField()
    duplicate = serializers.BooleanField()


class EventBatchResponseSerializer(serializers.Serializer):
    results = EventAcceptanceSerializer(many=True)


class EventDetailSerializer(serializers.ModelSerializer):
    workflow = WorkflowSummarySerializer(read_only=True)

    class Meta:
        model = Event
        fields = (
            "id",
            "event_type",
            "schema_version",
            "source",
            "idempotency_key",
            "occurred_at",
            "correlation_id",
            "request_id",
            "received_at",
            "payload",
            "workflow",
        )
