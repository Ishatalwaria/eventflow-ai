import uuid

from django.db import models


class IncidentSummary(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workflow = models.ForeignKey(
        "workflows.Workflow", on_delete=models.PROTECT, related_name="incident_summaries"
    )
    requested_by = models.ForeignKey(
        "common.APIClient", on_delete=models.PROTECT, related_name="incident_summaries"
    )
    evidence_hash = models.CharField(max_length=64)
    evidence = models.JSONField()
    summary = models.JSONField()
    prompt_version = models.CharField(max_length=64)
    provider = models.CharField(max_length=64)
    model = models.CharField(max_length=128)
    latency_ms = models.PositiveIntegerField()
    input_tokens = models.PositiveIntegerField(null=True, blank=True)
    output_tokens = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["workflow", "-created_at"], name="incident_workflow_created_idx")
        ]


class IncidentSummaryRateWindow(models.Model):
    client = models.OneToOneField(
        "common.APIClient",
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="incident_rate_window",
    )
    window_started_at = models.DateTimeField()
    request_count = models.PositiveSmallIntegerField(default=0)
