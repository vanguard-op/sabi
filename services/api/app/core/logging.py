"""Structured logging with correlation ids and redaction.

Logs carry a correlation id and never carry secrets, tokens, credentials, or
unmasked identity (NFR-024, NFR-028). Redaction is key-based because secrets do
not belong in the log stream at all.
"""

from __future__ import annotations

import contextvars
import json
import logging
from typing import Any

from app.core.ids import new_id

_correlation_id: contextvars.ContextVar[str] = contextvars.ContextVar("correlation_id", default="")

_REDACTED = "[redacted]"

# Keys whose values must never reach a log line. Matched case-insensitively as
# substrings so `x-session-secret` and `processor_token` are both caught.
SENSITIVE_KEY_PARTS = (
    "authorization",
    "cookie",
    "session_secret",
    "recovery_code",
    "recovery_secret",
    "secret_hash",
    "password",
    "passphrase",
    "token",
    "pepper",
    "api_key",
    "apikey",
    "private_key",
    "mandate_signing",
    "processor_token",
)


def set_correlation_id(value: str | None = None) -> str:
    correlation_id = value or new_id()
    _correlation_id.set(correlation_id)
    return correlation_id


def get_correlation_id() -> str:
    return _correlation_id.get()


def _is_sensitive(key: str) -> bool:
    lowered = key.lower()
    return any(part in lowered for part in SENSITIVE_KEY_PARTS)


def redact(value: Any) -> Any:
    """Recursively replace values under sensitive keys."""
    if isinstance(value, dict):
        return {
            key: (_REDACTED if _is_sensitive(str(key)) else redact(item))
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact(item) for item in value]
    return value


class CorrelationIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = get_correlation_id()
        return True


class RedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, dict):
            record.args = redact(record.args)
        for key, _value in list(record.__dict__.items()):
            if _is_sensitive(key):
                record.__dict__[key] = _REDACTED
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
            "correlationId": getattr(record, "correlation_id", ""),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        for key, value in record.__dict__.items():
            if key in _RESERVED_RECORD_KEYS or key.startswith("_"):
                continue
            payload.setdefault(key, value)
        return json.dumps(redact(payload), default=str)


_RESERVED_RECORD_KEYS = frozenset(logging.LogRecord("", 0, "", 0, "", (), None).__dict__.keys()) | {
    "message",
    "asctime",
    "correlation_id",
}


def configure_logging(level: str = "info") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    handler.addFilter(CorrelationIdFilter())
    handler.addFilter(RedactionFilter())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
