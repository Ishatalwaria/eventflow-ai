from rest_framework import serializers

from .models import Workflow, WorkflowAttempt


class WorkflowAttemptSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkflowAttempt
        fields = (
            "id",
            "stage",
            "direction",
            "attempt_number",
            "outcome",
            "started_at",
            "finished_at",
            "duration_ms",
            "error_code",
            "error_detail",
        )


class WorkflowDetailSerializer(serializers.ModelSerializer):
    event_id = serializers.UUIDField(read_only=True)
    attempts = WorkflowAttemptSerializer(many=True, read_only=True)

    class Meta:
        model = Workflow
        fields = (
            "id",
            "event_id",
            "workflow_type",
            "state",
            "current_stage",
            "created_at",
            "updated_at",
            "started_at",
            "finished_at",
            "last_error_code",
            "attempts",
        )


class WorkflowListQuerySerializer(serializers.Serializer):
    state = serializers.ChoiceField(choices=Workflow.State.choices, required=False)
