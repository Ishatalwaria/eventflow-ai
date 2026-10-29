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
