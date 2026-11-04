from django.core.management.base import BaseCommand

from apps.commerce.inventory import seed_demo_catalog_for_client
from apps.common.models import APIClient


class Command(BaseCommand):
    help = "Seed demo products and inventory for active API clients."

    def add_arguments(self, parser):
        parser.add_argument(
            "--client",
            type=str,
            default=None,
            help="Optional client UUID to seed only for a specific client.",
        )

    def handle(self, *args, **options):
        client_id = options.get("client")
        if client_id:
            clients = APIClient.objects.filter(pk=client_id, revoked_at__isnull=True)
        else:
            clients = APIClient.objects.filter(revoked_at__isnull=True)

        count = 0
        for client in clients:
            seed_demo_catalog_for_client(client)
            count += 1
        self.stdout.write(
            self.style.SUCCESS(f"Seeded demo catalog for {count} active client(s).")
        )
