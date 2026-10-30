import json
import logging
import re

from apps.common.observability import current_log_context

_SENSITIVE = re.compile(
    r"(?i)(authorization\s*[:=]\s*bearer\s+|\bbearer\s+)"
    r"[A-Za-z0-9._~+/-]+=*|"
    r"\b(password|passwd|secret|api[_-]?key|access[_-]?token|refresh[_-]?token)"
    r"(\s*[:=]\s*)[^\s,;]+"
)
_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_PHONE = re.compile(r"(?<!\w)(?:\+?\d[\d .()/-]{7,}\d)(?!\w)")


def _redact(message):
    redacted = _SENSITIVE.sub(
        lambda match: f"{match.group(1)}[REDACTED]" if match.group(1) else "credential=[REDACTED]",
        message,
    )
    return _PHONE.sub("[REDACTED_PHONE]", _EMAIL.sub("[REDACTED_EMAIL]", redacted))


class JsonFormatter(logging.Formatter):
    """Render log records as valid JSON without interpolating untrusted messages."""

    def format(self, record):
        fields = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": _redact(record.getMessage()),
        }
        fields.update(
            {
                key: value
                for key, value in current_log_context().items()
                if key
                in {
                    "request_id",
                    "trace_id",
                    "event_id",
                    "workflow_id",
                    "correlation_id",
                }
            }
        )
        return json.dumps(fields, ensure_ascii=False)
