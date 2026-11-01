from django.contrib.auth import get_user_model
from django.db.models import Q

from apps.common.models import APIClient

User = get_user_model()


def resolve_client_filter(request, prefix="client"):
    """
    Build a Q filter matching records accessible to the authenticated principal.

    - APIClient: matched directly on client == request.user
    - User: matched on client__owner == request.user (or unrestricted for staff)
    - Unauthenticated/Anonymous: matches nothing
    """
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return Q(pk__in=[])

    if isinstance(user, APIClient):
        return Q(**{prefix: user})

    if isinstance(user, User):
        if user.is_staff:
            return Q()
        owner_field = f"{prefix}__owner"
        return Q(**{owner_field: user})

    return Q(pk__in=[])


def get_effective_client(request):
    """
    Get or resolve the active APIClient for state-creating operations (e.g. event ingest).

    - If request.user is APIClient, returns request.user.
    - If request.user is User, returns their first active owned APIClient (creating a default if needed).
    - Otherwise returns None.
    """
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return None

    if isinstance(user, APIClient):
        return user

    if isinstance(user, User):
        active_client = user.api_clients.filter(revoked_at__isnull=True).order_by("created_at").first()
        if active_client is None:
            from apps.common.services import create_api_client
            active_client, _ = create_api_client(
                f"{user.username}'s Ingestion Client",
                owner=user,
                can_view_analytics=True,
            )
        return active_client

    return None
