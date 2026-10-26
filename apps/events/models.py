import uuid

from django.db import models


class Event(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    client = models.ForeignKey("common.APIClient", on_delete=models.PROTECT, related_name="events")
    event_type = models.CharField(max_length=200)
    schema_version = models.PositiveSmallIntegerField()
    source = models.CharField(max_length=100)
    idempotency_key = models.CharField(max_length=255)
    occurred_at = models.DateTimeField()
    correlation_id = models.CharField(max_length=128)
    request_id = models.CharField(max_length=64)
    payload = models.JSONField()
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["client", "source", "idempotency_key"],
                name="event_client_source_idem_uniq",
            )
        ]
        indexes = [
            models.Index(fields=["event_type", "received_at"], name="event_type_recv_idx"),
            models.Index(fields=["correlation_id"], name="event_correlation_idx"),
        ]

    def __str__(self):
        return f"{self.event_type} ({self.pk})"
