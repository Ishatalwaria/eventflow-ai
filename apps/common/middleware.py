import re
import uuid

from apps.common.observability import HTTP_REQUESTS, bind_log_context

REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")
CORRELATION_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


class RequestIDMiddleware:
    """Attach a safe request ID and return it to the caller."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        supplied = request.headers.get("X-Request-ID", "")
        request.request_id = (
            supplied if REQUEST_ID_PATTERN.fullmatch(supplied) else str(uuid.uuid4())
        )
        request.trace_id = request.request_id
        correlation_id = request.headers.get("X-Correlation-ID", "")
        correlation_id = (
            correlation_id if CORRELATION_ID_PATTERN.fullmatch(correlation_id) else None
        )
        try:
            with bind_log_context(
                request_id=request.request_id,
                trace_id=request.trace_id,
                correlation_id=correlation_id,
            ):
                response = self.get_response(request)
        except Exception:
            self._record_metric(request, 500)
            raise
        else:
            self._record_metric(request, response.status_code)
        response["X-Request-ID"] = request.request_id
        response["X-Trace-ID"] = request.trace_id
        return response

    @staticmethod
    def _record_metric(request, status_code):
        if request.path != "/metrics":
            route = getattr(getattr(request, "resolver_match", None), "route", None) or "unmatched"
            HTTP_REQUESTS.labels(
                method=request.method,
                route=route[:100],
                status=str(status_code),
            ).inc()
