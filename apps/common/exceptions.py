import logging

from rest_framework import status
from rest_framework.exceptions import (
    AuthenticationFailed,
    NotAuthenticated,
    NotFound,
    ParseError,
    Throttled,
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
    elif isinstance(exc, Throttled):
        code = "THROTTLED"
        wait = getattr(exc, "wait", None)
        if wait:
            wait_seconds = max(1, int(wait))
            message = f"Rate limit exceeded. Retry in about {wait_seconds} seconds."
        else:
            message = "Rate limit exceeded. Please wait before retrying."
    elif response.status_code == 413:
        code, message = "REQUEST_TOO_LARGE", "The request body exceeds the allowed size."
    else:
        exception_code = getattr(exc, "default_code", "error")
        code = (
            str(exception_code).upper()
            if isinstance(exception_code, str) and exception_code != "error"
            else "API_ERROR"
        )
        message = "The request could not be completed."

    response.data = {
        "error": {
            "code": code,
            "message": message,
            "request_id": getattr(request, "request_id", None),
            "details": response.data,
        }
    }
    return response
