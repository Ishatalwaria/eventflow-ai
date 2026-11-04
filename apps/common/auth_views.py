import logging

from django.contrib.auth import get_user_model, login, logout
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError
from django.middleware.csrf import get_token
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.models import APIClient
from apps.common.services import create_api_client, revoke_api_client

logger = logging.getLogger(__name__)
User = get_user_model()


class CSRFView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        summary="Get CSRF Token",
        description=(
            "Initialize CSRF cookie and retrieve CSRF token for single-page application requests."
        ),
        responses={
            200: inline_serializer("CSRFResponse", fields={"csrfToken": serializers.CharField()})
        },
    )
    def get(self, request):
        return Response({"csrfToken": get_token(request)})


class RegisterView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        summary="Register User",
        description=(
            "Register a new user account with session establishment "
            "and auto-provisioned workspace API key."
        ),
        responses={
            201: inline_serializer(
                "RegisterResponse",
                fields={
                    "id": serializers.IntegerField(),
                    "name": serializers.CharField(),
                    "email": serializers.EmailField(),
                    "is_staff": serializers.BooleanField(),
                    "default_client_id": serializers.UUIDField(),
                },
            )
        },
    )
    def post(self, request):
        data = request.data or {}
        name = str(data.get("name") or data.get("first_name") or data.get("username") or "").strip()
        email = str(data.get("email") or data.get("username") or "").strip().lower()
        password = str(data.get("password", ""))
        password_confirm = str(data.get("password_confirm") or data.get("confirm_password") or "")

        if not name or not email or not password:
            return Response(
                {
                    "error": {
                        "code": "VALIDATION_ERROR",
                        "message": "Name, email, and password are required.",
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if "@" not in email or "." not in email.split("@")[-1]:
            return Response(
                {
                    "error": {
                        "code": "INVALID_EMAIL",
                        "message": "Please enter a valid email address.",
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if password != password_confirm:
            return Response(
                {"error": {"code": "PASSWORD_MISMATCH", "message": "Passwords do not match."}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if (
            User.objects.filter(email__iexact=email).exists()
            or User.objects.filter(username__iexact=email).exists()
        ):
            return Response(
                {
                    "error": {
                        "code": "EMAIL_ALREADY_EXISTS",
                        "message": "An account with this email already exists.",
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        dummy_user = User(username=email, email=email, first_name=name)
        try:
            validate_password(password, user=dummy_user)
        except ValidationError as exc:
            return Response(
                {"error": {"code": "WEAK_PASSWORD", "message": " ".join(exc.messages)}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = User.objects.create_user(
            username=email,
            email=email,
            password=password,
            first_name=name,
        )

        # Auto-provision a default ingestion client for the new user's workspace
        client, _ = create_api_client(
            f"{name}'s Default Client", owner=user, can_view_analytics=True
        )
        try:
            from apps.commerce.inventory import seed_demo_catalog_for_client

            seed_demo_catalog_for_client(client)
        except Exception as exc:
            logger.warning("Could not auto-seed demo catalog for client: %s", exc)

        login(request, user)

        return Response(
            {
                "id": user.id,
                "name": user.first_name or user.username,
                "email": user.email,
                "type": "user",
                "is_staff": user.is_staff,
                "default_client_id": str(client.id),
                "client_id": str(client.id),
            },
            status=status.HTTP_201_CREATED,
        )


class LoginView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        summary="User Login",
        description="Authenticate via email and password, establishing an HttpOnly session cookie.",
        responses={
            200: inline_serializer(
                "LoginResponse",
                fields={
                    "id": serializers.IntegerField(),
                    "name": serializers.CharField(),
                    "email": serializers.EmailField(),
                    "is_staff": serializers.BooleanField(),
                },
            )
        },
    )
    def post(self, request):
        data = request.data or {}
        identifier = str(data.get("email") or data.get("username") or "").strip().lower()
        password = str(data.get("password", ""))

        if not identifier or not password:
            return Response(
                {
                    "error": {
                        "code": "VALIDATION_ERROR",
                        "message": "Email and password are required.",
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = (
            User.objects.filter(email__iexact=identifier).first()
            or User.objects.filter(username__iexact=identifier).first()
        )
        if user is None or not user.check_password(password):
            # Constant-time mitigation
            User().set_password("dummy-protection")
            return Response(
                {"error": {"code": "INVALID_CREDENTIALS", "message": "Invalid email or password."}},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        if not user.is_active:
            return Response(
                {"error": {"code": "ACCOUNT_DISABLED", "message": "This account is inactive."}},
                status=status.HTTP_403_FORBIDDEN,
            )

        login(request, user)

        return Response(
            {
                "id": user.id,
                "name": user.first_name or user.username,
                "email": user.email,
                "type": "user",
                "is_staff": user.is_staff,
            }
        )


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="User Logout",
        description="Terminate current session and invalidate session cookie.",
        responses={
            200: inline_serializer("LogoutResponse", fields={"detail": serializers.CharField()})
        },
    )
    def post(self, request):
        logout(request)
        return Response({"detail": "Successfully logged out."})


class CurrentUserView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Current User Profile",
        description="Retrieve profile details for the currently authenticated session.",
        responses={
            200: inline_serializer(
                "CurrentUserResponse",
                fields={
                    "id": serializers.CharField(),
                    "name": serializers.CharField(),
                    "email": serializers.CharField(allow_blank=True),
                    "is_staff": serializers.BooleanField(),
                    "is_api_client": serializers.BooleanField(),
                    "type": serializers.CharField(),
                },
            )
        },
    )
    def get(self, request):
        user = request.user
        if isinstance(user, User):
            return Response(
                {
                    "id": str(user.id),
                    "username": user.username,
                    "name": user.first_name or user.username,
                    "email": user.email,
                    "type": "user",
                    "is_staff": user.is_staff,
                    "is_api_client": False,
                    "date_joined": user.date_joined,
                }
            )
        if isinstance(user, APIClient):
            return Response(
                {
                    "id": str(user.id),
                    "name": user.name,
                    "email": "",
                    "type": "api_client",
                    "is_staff": False,
                    "is_api_client": True,
                    "can_view_analytics": user.can_view_analytics,
                    "created_at": user.created_at,
                }
            )
        raise AuthenticationFailed()


class PasswordResetRequestView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        email = str(request.data.get("email", "")).strip().lower()
        if email:
            user = User.objects.filter(email__iexact=email).first()
            if user:
                _token = default_token_generator.make_token(user)
                uid = urlsafe_base64_encode(force_bytes(user.pk))
                logger.info("Password reset requested for user_id=%s uid=%s", user.pk, uid)
                # In production, send email; in local demo, log token safely
        return Response(
            {
                "detail": (
                    "If that email exists in our system, "
                    "password reset instructions have been sent."
                )
            },
            status=status.HTTP_200_OK,
        )


class PasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        data = request.data or {}
        uid_b64 = data.get("uid", "")
        token = data.get("token", "")
        password = str(data.get("password", ""))
        password_confirm = str(data.get("password_confirm", ""))

        if not uid_b64 or not token or not password:
            return Response(
                {
                    "error": {
                        "code": "VALIDATION_ERROR",
                        "message": "UID, token, and new password are required.",
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if password != password_confirm:
            return Response(
                {"error": {"code": "PASSWORD_MISMATCH", "message": "Passwords do not match."}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            uid = force_str(urlsafe_base64_decode(uid_b64))
            user = User.objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            return Response(
                {"error": {"code": "INVALID_TOKEN", "message": "Invalid or expired reset link."}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not default_token_generator.check_token(user, token):
            return Response(
                {"error": {"code": "INVALID_TOKEN", "message": "Invalid or expired reset link."}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            validate_password(password, user=user)
        except ValidationError as exc:
            return Response(
                {"error": {"code": "WEAK_PASSWORD", "message": " ".join(exc.messages)}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user.set_password(password)
        user.save()
        return Response(
            {
                "detail": (
                    "Password has been reset successfully. "
                    "You can now sign in with your new password."
                )
            }
        )


class ClientListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not isinstance(request.user, User):
            raise PermissionDenied("Only authenticated users can manage API clients.")

        qs = (
            APIClient.objects.all()
            if request.user.is_staff
            else APIClient.objects.filter(owner=request.user)
        )
        qs = qs.order_by("-created_at")

        clients = [
            {
                "id": str(c.id),
                "name": c.name,
                "can_view_analytics": c.can_view_analytics,
                "created_at": c.created_at,
                "rotated_at": c.rotated_at,
                "revoked_at": c.revoked_at,
                "is_active": c.is_active,
            }
            for c in qs
        ]
        return Response({"count": len(clients), "results": clients})

    def post(self, request):
        if not isinstance(request.user, User):
            raise PermissionDenied("Only authenticated users can create API clients.")

        name = str(request.data.get("name", "")).strip()
        if not name:
            return Response(
                {"error": {"code": "VALIDATION_ERROR", "message": "Client name is required."}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        can_view_analytics = bool(request.data.get("can_view_analytics", False))
        client, raw_token = create_api_client(
            name,
            owner=request.user,
            can_view_analytics=can_view_analytics,
        )
        if request.data.get("seed_demo", False):
            try:
                from apps.commerce.inventory import seed_demo_catalog_for_client

                seed_demo_catalog_for_client(client)
            except Exception as exc:
                logger.warning("Could not seed demo catalog for new client: %s", exc)

        return Response(
            {
                "id": str(client.id),
                "name": client.name,
                "token": raw_token,
                "can_view_analytics": client.can_view_analytics,
                "created_at": client.created_at,
                "message": "Copy this token now. It will never be displayed again.",
            },
            status=status.HTTP_201_CREATED,
        )


class ClientRevokeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, client_id):
        if not isinstance(request.user, User):
            raise PermissionDenied("Only authenticated users can revoke API clients.")

        qs = (
            APIClient.objects.all()
            if request.user.is_staff
            else APIClient.objects.filter(owner=request.user)
        )
        client = qs.filter(pk=client_id).first()
        if client is None:
            return Response(
                {
                    "error": {
                        "code": "NOT_FOUND",
                        "message": "API client not found or not owned by you.",
                    }
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        revoke_api_client(client)
        return Response({"detail": f"API client {client.name} ({client.pk}) has been revoked."})
