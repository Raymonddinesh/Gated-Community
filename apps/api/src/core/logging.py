"""Structured JSON Logging with Correlation ID and PII Redaction."""

import json
import logging
import re
import sys
from datetime import UTC, datetime
from typing import Any

# Regex patterns for sensitive PII data redaction
PII_PATTERNS = [
    (
        re.compile(
            r'("?(?:password|token|secret|access_token|refresh_token)"?\s*[:=]\s*"?[^",\s]+"?\b)',
            re.IGNORECASE,
        ),
        "[REDACTED]",
    ),
    (re.compile(r"(\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b)"), "[REDACTED_CARD]"),
    (re.compile(r"(\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b)"), "[REDACTED_EMAIL]"),
]


def redact_pii(message: str) -> str:
    """Scrub sensitive credentials, tokens, and PII from log output."""
    clean_message = message
    for pattern, replacement in PII_PATTERNS:
        clean_message = pattern.sub(replacement, clean_message)
    return clean_message


class JsonLogFormatter(logging.Formatter):
    """Formats log records as structured single-line JSON."""

    def __init__(self, env: str = "development") -> None:
        super().__init__()
        self.env = env

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": redact_pii(record.getMessage()),
            "environment": self.env,
        }

        # Inject correlation ID if attached to record or extra
        correlation_id = getattr(record, "correlation_id", None)
        if correlation_id:
            log_entry["correlation_id"] = correlation_id

        # Inject request details if present
        if hasattr(record, "http_method"):
            log_entry["http_method"] = record.http_method
        if hasattr(record, "path"):
            log_entry["path"] = record.path
        if hasattr(record, "status_code"):
            log_entry["status_code"] = record.status_code
        if hasattr(record, "duration_ms"):
            log_entry["duration_ms"] = record.duration_ms

        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry)


def setup_logging(log_level: str = "INFO", app_env: str = "development") -> logging.Logger:
    """Configure root logger with structured JSON handler."""
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Remove existing handlers to avoid duplicates
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(JsonLogFormatter(env=app_env))
    root_logger.addHandler(stream_handler)

    # Quiet overly chatty loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)

    return root_logger
