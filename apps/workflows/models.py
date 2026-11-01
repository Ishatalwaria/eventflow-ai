import uuid

from django.db import models


class Workflow(models.Model):
    class State(models.TextChoices):
        RECEIVED = "RECEIVED", "Received"
        QUEUED = "QUEUED", "Queued"
        PROCESSING = "PROCESSING", "Processing"
        RETRY_WAIT = "RETRY_WAIT", "Retry wait"
        SUCCEEDED = "SUCCEEDED", "Succeeded"
        FAILED = "FAILED", "Failed"
        DEAD_LETTERED = "DEAD_LETTERED", "Dead lettered"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.OneToOneField("events.Event", on_delete=models.PROTECT, related_name="workflow")
    workflow_type = models.CharField(max_length=100, default="event_processing")
    state = models.CharField(max_length=24, choices=State.choices, default=State.RECEIVED)
    current_stage = models.CharField(max_length=100, default="accepted")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    last_error_code = models.CharField(max_length=100, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(
                    state__in=[
                        "RECEIVED",
                        "QUEUED",
                        "PROCESSING",
                        "RETRY_WAIT",
                        "SUCCEEDED",
                        "FAILED",
                        "DEAD_LETTERED",
                    ]
                ),
                name="workflow_state_valid",
            )
        ]
        indexes = [models.Index(fields=["state", "created_at"], name="workflow_state_created_idx")]

    def __str__(self):
        return f"{self.workflow_type} ({self.pk})"


class WorkflowAttempt(models.Model):
    class Outcome(models.TextChoices):
        STARTED = "STARTED", "Started"
        SUCCEEDED = "SUCCEEDED", "Succeeded"
        RETRYING = "RETRYING", "Retrying"
        FAILED = "FAILED", "Failed"
        DEAD_LETTERED = "DEAD_LETTERED", "Dead lettered"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workflow = models.ForeignKey(Workflow, on_delete=models.CASCADE, related_name="attempts")
    stage = models.CharField(max_length=100)
    attempt_number = models.PositiveSmallIntegerField()
    outcome = models.CharField(max_length=16, choices=Outcome.choices, default=Outcome.STARTED)
    started_at = models.DateTimeField()
    finished_at = models.DateTimeField(null=True, blank=True)
    duration_ms = models.PositiveIntegerField(null=True, blank=True)
    error_code = models.CharField(max_length=100, blank=True)
    error_detail = models.CharField(max_length=500, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["workflow", "stage", "attempt_number"],
                name="workflow_stage_attempt_uniq",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    outcome__in=["STARTED", "SUCCEEDED", "RETRYING", "FAILED", "DEAD_LETTERED"]
                ),
                name="attempt_outcome_valid",
            ),
        ]
        indexes = [
            models.Index(fields=["workflow", "started_at"], name="attempt_wf_started_idx"),
            models.Index(fields=["started_at"], name="workflow_attempt_started_idx"),
        ]

    def __str__(self):
        return f"{self.workflow_id}:{self.stage}#{self.attempt_number}"
