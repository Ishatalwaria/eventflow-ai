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


class EventListQuerySerializer(serializers.Serializer):
    search = serializers.CharField(
        required=False, allow_blank=True, max_length=128, trim_whitespace=True
    )
    event_type = serializers.CharField(required=False, max_length=200)
    date_from = serializers.DateField(required=False)
    date_to = serializers.DateField(required=False)

    def validate(self, attrs):
        if (
            attrs.get("date_from")
            and attrs.get("date_to")
            and attrs["date_from"] > attrs["date_to"]
        ):
            raise serializers.ValidationError({"date_to": "Must be on or after date_from."})
        return attrs


class EventListSerializer(serializers.ModelSerializer):
    workflow = WorkflowSummarySerializer(read_only=True)

    class Meta:
        model = Event
        fields = (
            "id",
            "event_type",
            "schema_version",
            "source",
            "idempotency_key",
            "correlation_id",
            "received_at",
            "workflow",
        )
