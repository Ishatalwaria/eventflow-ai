from rest_framework import serializers

from .models import IncidentSummary


class IncidentSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = IncidentSummary
        fields = [
            "id",
            "workflow_id",
            "evidence_hash",
            "evidence",
            "summary",
            "prompt_version",
            "provider",
            "model",
            "latency_ms",
            "input_tokens",
            "output_tokens",
            "created_at",
        ]
        read_only_fields = fields


class IncidentSummaryListSerializer(serializers.ModelSerializer):
    event_id = serializers.UUIDField(source="workflow.event_id", read_only=True)
    workflow_state = serializers.CharField(source="workflow.state", read_only=True)
    headline = serializers.CharField(source="summary.headline", read_only=True)

    class Meta:
        model = IncidentSummary
        fields = (
            "id",
            "workflow_id",
            "event_id",
            "workflow_state",
            "headline",
            "provider",
            "model",
            "created_at",
        )


class IncidentSummaryListQuerySerializer(serializers.Serializer):
    search = serializers.CharField(
        required=False, allow_blank=True, max_length=128, trim_whitespace=True
    )
    workflow_state = serializers.ChoiceField(
        choices=(("FAILED", "FAILED"), ("DEAD_LETTERED", "DEAD_LETTERED")), required=False
    )
