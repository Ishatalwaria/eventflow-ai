from rest_framework.permissions import BasePermission


class CanViewAnalytics(BasePermission):
    message = "This API client does not have analytics access."

    def has_permission(self, request, view):
        return bool(getattr(request.user, "can_view_analytics", False))
