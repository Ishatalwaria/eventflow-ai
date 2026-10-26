import uuid

from django.core.management.base import BaseCommand, CommandError

from apps.common.models import APIClient
from apps.common.services import create_api_client, revoke_api_client, rotate_api_client


class Command(BaseCommand):
    help = "Create, rotate, or revoke an EventFlow API client credential."

    def add_arguments(self, parser):
        parser.add_argument("action", choices=("create", "rotate", "revoke"))
        parser.add_argument("--name", help="Name for a new client.")
        parser.add_argument("--client-id", help="UUID of an existing client.")

    def handle(self, *args, **options):
        action = options["action"]
        if action == "create":
            if not options["name"]:
                raise CommandError("--name is required for create.")
            client, token = create_api_client(options["name"])
            self.stdout.write(f"Client ID: {client.pk}")
            self.stdout.write(self.style.SUCCESS(f"Token (shown once): {token}"))
            return

        if not options["client_id"]:
            raise CommandError("--client-id is required for rotate and revoke.")
        try:
            client_id = uuid.UUID(options["client_id"])
        except ValueError:
            raise CommandError("--client-id must be a UUID.") from None
        try:
            client = APIClient.objects.get(pk=client_id)
        except APIClient.DoesNotExist:
            raise CommandError("Client not found.") from None

        if action == "rotate":
            try:
                token = rotate_api_client(client)
            except ValueError as exc:
                raise CommandError(str(exc)) from None
            self.stdout.write(self.style.SUCCESS(f"Replacement token (shown once): {token}"))
        else:
            revoke_api_client(client)
            self.stdout.write(self.style.SUCCESS(f"Client revoked: {client.pk}"))
