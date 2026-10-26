import logging

from django.db import DatabaseError, connection
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

logger = logging.getLogger(__name__)


class LivenessView(APIView):
    authentication_classes = []
    permission_classes = []

    @extend_schema(
        responses={
            200: inline_serializer("LivenessResponse", fields={"status": serializers.CharField()})
        }
    )
    def get(self, request):
        return Response({"status": "ok"}, status=status.HTTP_200_OK)


class ReadinessView(APIView):
    authentication_classes = []
    permission_classes = []

    @extend_schema(
        responses={
            200: inline_serializer(
                "ReadinessResponse",
                fields={
                    "status": serializers.CharField(),
                    "checks": serializers.DictField(child=serializers.CharField()),
                },
            ),
            503: inline_serializer(
                "ReadinessUnavailableResponse",
                fields={
                    "status": serializers.CharField(),
                    "checks": serializers.DictField(child=serializers.CharField()),
                },
            ),
        }
    )
    def get(self, request):
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        except DatabaseError:
            logger.warning("Readiness check failed: database unavailable")
            return Response(
                {"status": "not_ready", "checks": {"database": "unavailable"}},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        return Response(
            {"status": "ready", "checks": {"database": "ok"}}, status=status.HTTP_200_OK
        )
