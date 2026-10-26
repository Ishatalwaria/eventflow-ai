import io

from django.conf import settings
from rest_framework.exceptions import APIException
from rest_framework.parsers import JSONParser


class RequestTooLarge(APIException):
    status_code = 413
    default_detail = "Request body exceeds the configured size limit."
    default_code = "request_too_large"


class BoundedJSONParser(JSONParser):
    """Read at most the configured event request size plus one byte."""

    def parse(self, stream, media_type=None, parser_context=None):
        maximum = settings.EVENT_MAX_REQUEST_BYTES
        body = stream.read(maximum + 1)
        if len(body) > maximum:
            raise RequestTooLarge()
        return super().parse(io.BytesIO(body), media_type, parser_context)
