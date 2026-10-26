import logging

from rest_framework import status
from rest_framework.exceptions import (
    AuthenticationFailed,
    NotAuthenticated,
    NotFound,
    ParseError,
    ValidationError,
)
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

logger = logging.getLogger(__name__)


def api_exception_handler(exc, context):
    response = drf_exception_handler(exc, context)
    request = context.get("request")
    if response is None:
        request_id = getattr(request, "request_id", None)
        logger.error(
            "Unhandled API exception type=%s request_id=%s",
            type(exc).__name__,
            request_id,
        )
        return Response(
            {
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "The request could not be completed.",
                    "request_id": request_id,
                    "details": {},
                }
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    if isinstance(exc, ValidationError):
        code, message = "VALIDATION_ERROR", "Request validation failed."
    elif isinstance(exc, (AuthenticationFailed, NotAuthenticated)):
        code, message = "AUTHENTICATION_FAILED", "Valid client authentication is required."
    elif isinstance(exc, NotFound):
        code, message = "RESOURCE_NOT_FOUND", "The requested resource was not found."
    elif isinstance(exc, ParseError):
        code, message = "INVALID_REQUEST_BODY", "The request body is invalid."
    elif response.status_code == 413:
        code, message = "REQUEST_TOO_LARGE", "The request body exceeds the allowed size."
    else:
        code, message = "API_ERROR", "The request could not be completed."

    response.data = {
        "error": {
            "code": code,
            "message": message,
            "request_id": getattr(request, "request_id", None),
            "details": response.data,
        }
    }
    return response
