"""
Structured JSON logging with request_id/session_id correlation — per the roadmap's rule
("Structured (JSON) logging with session_id/request_id correlation from Phase 11 onward").

Correlation IDs live in contextvars, set once per request by the correlation middleware
(app/main.py) and automatically attached to every log record emitted during that request —
including from deep inside services/repositories that have no idea a request is in flight.
"""

import contextvars
import json
import logging
import sys
from datetime import datetime, timezone

request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)
session_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("session_id", default=None)

_RESERVED = frozenset(logging.LogRecord(__name__, 0, __file__, 0, "", (), None).__dict__.keys()) | {"message", "asctime"}


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_var.get(),
            "session_id": session_id_var.get(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        for key, value in record.__dict__.items():
            if key not in _RESERVED and key not in payload:
                payload[key] = value
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    root.addHandler(handler)
