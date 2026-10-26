import re
import uuid

REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")


class RequestIDMiddleware:
    """Attach a safe request ID and return it to the caller."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        supplied = request.headers.get("X-Request-ID", "")
        request.request_id = (
            supplied if REQUEST_ID_PATTERN.fullmatch(supplied) else str(uuid.uuid4())
        )
        response = self.get_response(request)
        response["X-Request-ID"] = request.request_id
        return response
