from django.urls import path

from apps.common.auth_views import (
    ClientListCreateView,
    ClientRevokeView,
    CSRFView,
    CurrentUserView,
    LoginView,
    LogoutView,
    PasswordResetConfirmView,
    PasswordResetRequestView,
    RegisterView,
)

urlpatterns = [
    path("auth/csrf", CSRFView.as_view(), name="auth-csrf"),
    path("auth/register", RegisterView.as_view(), name="auth-register"),
    path("auth/login", LoginView.as_view(), name="auth-login"),
    path("auth/logout", LogoutView.as_view(), name="auth-logout"),
    path("auth/me", CurrentUserView.as_view(), name="auth-me"),
    path("auth/password-reset", PasswordResetRequestView.as_view(), name="auth-password-reset"),
    path("auth/password-reset/confirm", PasswordResetConfirmView.as_view(), name="auth-password-reset-confirm"),
    path("clients", ClientListCreateView.as_view(), name="clients-list-create"),
    path("clients/<uuid:client_id>/revoke", ClientRevokeView.as_view(), name="clients-revoke"),
]
