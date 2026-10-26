import uuid

from django.contrib.auth.hashers import check_password, make_password
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed

from .models import APIClient

_DUMMY_SECRET_HASH = make_password("invalid-api-client-secret")


class APIClientAuthentication(BaseAuthentication):
    """Authenticate ``Bearer <client-uuid>.<secret>`` credentials."""

    def authenticate(self, request):
        parts = get_authorization_header(request).split()
        if not parts:
            return None
        if len(parts) != 2 or parts[0].lower() != b"bearer":
            raise AuthenticationFailed("Use a Bearer client token.")

        try:
            client_id, secret = parts[1].decode("ascii").split(".", maxsplit=1)
            client_uuid = uuid.UUID(client_id)
        except UnicodeDecodeError, ValueError:
            raise AuthenticationFailed("Invalid client credentials.") from None

        client = APIClient.objects.filter(pk=client_uuid, revoked_at__isnull=True).first()
        if client is None:
            check_password(secret, _DUMMY_SECRET_HASH)
            raise AuthenticationFailed("Invalid client credentials.")
        if not check_password(secret, client.secret_hash):
            raise AuthenticationFailed("Invalid client credentials.")

        return client, None

    def authenticate_header(self, request):
        return "Bearer"
