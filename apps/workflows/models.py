import uuid

from django.conf import settings
from django.db import models


class Workflow(models.Model):
    class State(models.TextChoices):
        RECEIVED = "RECEIVED", "Received"
        QUEUED = "QUEUED", "Queued"
        PROCESSING = "PROCESSING", "Processing"
        RETRY_WAIT = "RETRY_WAIT", "Retry wait"
        COMPENSATING = "COMPENSATING", "Compensating"
        SUCCEEDED = "SUCCEEDED", "Succeeded"
        FAILED = "FAILED", "Failed"
        DEAD_LETTERED = "DEAD_LETTERED", "Dead lettered"
        CANCELLED = "CANCELLED", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.OneToOneField("events.Event", on_delete=models.PROTECT, related_name="workflow")
    workflow_type = models.CharField(max_length=100, default="order_fulfillment")
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
                        "COMPENSATING",
                        "SUCCEEDED",
                        "FAILED",
                        "DEAD_LETTERED",
                        "CANCELLED",
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

    class Direction(models.TextChoices):
        FORWARD = "forward", "Forward"
        COMPENSATE = "compensate", "Compensate"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workflow = models.ForeignKey(Workflow, on_delete=models.CASCADE, related_name="attempts")
    stage = models.CharField(max_length=100)
    direction = models.CharField(
        max_length=16, choices=Direction.choices, default=Direction.FORWARD
    )
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
                fields=["workflow", "stage", "direction", "attempt_number"],
                name="workflow_stage_dir_attempt_uniq",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    outcome__in=["STARTED", "SUCCEEDED", "RETRYING", "FAILED", "DEAD_LETTERED"]
                ),
                name="attempt_outcome_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(direction__in=["forward", "compensate"]),
                name="attempt_direction_valid",
            ),
        ]
        indexes = [
            models.Index(fields=["workflow", "started_at"], name="attempt_wf_started_idx"),
            models.Index(fields=["started_at"], name="workflow_attempt_started_idx"),
        ]

    def __str__(self):
        return f"{self.workflow_id}:{self.direction}:{self.stage}#{self.attempt_number}"


class OperatorAuditLog(models.Model):
    class Action(models.TextChoices):
        RETRY = "retry", "Retry"
        REPLAY = "replay", "Replay"
        CANCEL = "cancel", "Cancel"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workflow = models.ForeignKey(Workflow, on_delete=models.CASCADE, related_name="audit_logs")
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="workflow_audit_logs",
    )
    action = models.CharField(max_length=32, choices=Action.choices)
    idempotency_key = models.CharField(max_length=255)
    detail = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["idempotency_key"], name="operator_audit_idem_uniq"),
        ]
        indexes = [
            models.Index(fields=["workflow", "created_at"], name="operator_audit_wf_created_idx"),
        ]
