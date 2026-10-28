import json

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.processing.outbox import oldest_unpublished_summary


class Command(BaseCommand):
    help = "Report unpublished outbox backlog and its oldest age for alerting."

    def add_arguments(self, parser):
        parser.add_argument(
            "--max-age-seconds",
            type=int,
            default=settings.OUTBOX_ALERT_AGE_SECONDS,
        )
        parser.add_argument(
            "--check",
            action="store_true",
            help="Exit nonzero if the threshold is breached.",
        )

    def handle(self, *args, **options):
        summary = oldest_unpublished_summary()
        if options["max_age_seconds"] < 0:
            raise CommandError("max age must be non-negative")
        summary["alert_threshold_seconds"] = options["max_age_seconds"]
        summary["alert"] = (
            summary["dead_lettered_count"] > 0
            or summary["oldest_unpublished_age_seconds"] is not None
            and summary["oldest_unpublished_age_seconds"] > options["max_age_seconds"]
        )
        self.stdout.write(json.dumps(summary, sort_keys=True))
        if options["check"] and summary["alert"]:
            raise CommandError("outbox alert threshold exceeded")
