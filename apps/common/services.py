import secrets

from django.contrib.auth.hashers import make_password
from django.utils import timezone

from .models import APIClient


def create_api_client(name, *, can_view_analytics=False):
    secret = secrets.token_urlsafe(32)
    client = APIClient.objects.create(
        name=name,
        secret_hash=make_password(secret),
        can_view_analytics=can_view_analytics,
    )
    return client, f"{client.pk}.{secret}"


def rotate_api_client(client):
    if not client.is_active:
        raise ValueError("A revoked client cannot be rotated.")
    secret = secrets.token_urlsafe(32)
    client.secret_hash = make_password(secret)
    client.rotated_at = timezone.now()
    client.save(update_fields=["secret_hash", "rotated_at"])
    return f"{client.pk}.{secret}"


def revoke_api_client(client):
    if client.is_active:
        client.revoked_at = timezone.now()
        client.save(update_fields=["revoked_at"])
