import uuid

from django.db import models


class APIClient(models.Model):
    """A client identity with a hash-only bearer secret."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=120)
    secret_hash = models.CharField(max_length=256)
    created_at = models.DateTimeField(auto_now_add=True)
    rotated_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True, db_index=True)

    @property
    def is_authenticated(self):
        return True

    @property
    def is_active(self):
        return self.revoked_at is None

    def __str__(self):
        return f"{self.name} ({self.pk})"
