import json
import logging


class JsonFormatter(logging.Formatter):
    """Render log records as valid JSON without interpolating untrusted messages."""

    def format(self, record):
        return json.dumps(
            {
                "timestamp": self.formatTime(record, self.datefmt),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
            },
            ensure_ascii=False,
        )
