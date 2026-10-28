import uuid

from django.db import models
from django.db.models import Q
from django.utils import timezone


class OutboxMessage(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey("events.Event", on_delete=models.PROTECT, related_name="outbox")
    dedupe_key = models.CharField(max_length=255, unique=True, default=uuid.uuid4)
    topic = models.CharField(max_length=200)
    payload = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
    available_at = models.DateTimeField(default=timezone.now)
    lease_owner = models.UUIDField(null=True, blank=True)
    lease_expires_at = models.DateTimeField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    dead_lettered_at = models.DateTimeField(null=True, blank=True)
    publish_attempts = models.PositiveSmallIntegerField(default=0)
    last_error_code = models.CharField(max_length=100, blank=True)
    last_error_detail = models.CharField(max_length=500, blank=True)

    class Meta:
        indexes = [
            models.Index(
                fields=["available_at", "created_at"],
                condition=Q(published_at__isnull=True, dead_lettered_at__isnull=True),
                name="outbox_ready_idx",
            ),
            models.Index(fields=["lease_expires_at"], name="outbox_lease_idx"),
        ]

    def __str__(self):
        return f"{self.topic} ({self.pk})"


class ProcessingLog(models.Model):
    class Level(models.TextChoices):
        INFO = "INFO", "Info"
        WARNING = "WARNING", "Warning"
        ERROR = "ERROR", "Error"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey("events.Event", on_delete=models.PROTECT, related_name="logs")
    workflow = models.ForeignKey(
        "workflows.Workflow", on_delete=models.PROTECT, related_name="logs"
    )
    attempt = models.ForeignKey(
        "workflows.WorkflowAttempt",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="logs",
    )
    level = models.CharField(max_length=8, choices=Level.choices, default=Level.INFO)
    message = models.CharField(max_length=500)
    request_id = models.CharField(max_length=64)
    correlation_id = models.CharField(max_length=128)
    attributes = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(level__in=["INFO", "WARNING", "ERROR"]),
                name="processing_log_level_valid",
            )
        ]
        indexes = [
            models.Index(fields=["event", "created_at"], name="log_event_created_idx"),
            models.Index(fields=["workflow", "created_at"], name="log_wf_created_idx"),
        ]

    def __str__(self):
        return f"{self.level}: {self.message[:80]}"
