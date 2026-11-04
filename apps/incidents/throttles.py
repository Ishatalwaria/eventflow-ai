from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.throttling import BaseThrottle

from apps.common.scope import get_effective_client

from .models import IncidentSummaryRateWindow


class IncidentSummaryThrottle(BaseThrottle):
    """Shared, database-backed cap: five incident analyses per client per hour."""

    duration = timedelta(hours=1)

    def allow_request(self, request, view):
        if not getattr(request.user, "is_authenticated", False):
            return True
        client = get_effective_client(request)
        if client is None:
            return True
        now = timezone.now()
        with transaction.atomic():
            IncidentSummaryRateWindow.objects.get_or_create(
                client_id=client.pk,
                defaults={"window_started_at": now, "request_count": 0},
            )
            window = IncidentSummaryRateWindow.objects.select_for_update().get(client_id=client.pk)
            if now - window.window_started_at >= self.duration:
                window.window_started_at = now
                window.request_count = 0
            if window.request_count >= settings.INCIDENT_SUMMARY_RATE_LIMIT:
                self.wait_seconds = max(
                    0, int((window.window_started_at + self.duration - now).total_seconds())
                )
                return False
            window.request_count += 1
            window.save(update_fields=["window_started_at", "request_count"])
        self.wait_seconds = None
        return True

    def wait(self):
        return self.wait_seconds
