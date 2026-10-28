import json
from datetime import date

from django.core.management.base import BaseCommand, CommandError

from apps.analytics.queries import lifecycle_report


class Command(BaseCommand):
    help = "Print ClickHouse lifecycle analytics for a bounded date range."

    def add_arguments(self, parser):
        parser.add_argument("--from", dest="start", required=True, help="Start date YYYY-MM-DD.")
        parser.add_argument("--to", dest="end", required=True, help="End date YYYY-MM-DD.")

    def handle(self, *args, **options):
        try:
            start_date = date.fromisoformat(options["start"])
            end_date = date.fromisoformat(options["end"])
            report = lifecycle_report(start_date, end_date)
        except (ValueError, RuntimeError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(json.dumps(report, default=str, indent=2))
