"""Structured logging with correlation IDs."""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from typing import Any

LOGGER_NAME = "princesse"
_configured = False


class JsonFormatter(logging.Formatter):
    """One JSON object per log line."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        correlation = getattr(record, "correlation_id", None)
        if correlation:
            payload["correlation_id"] = correlation
        for key, value in getattr(record, "extra_fields", {}).items():
            payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


class TextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        base = f"{record.levelname:<7} {record.name}: {record.getMessage()}"
        correlation = getattr(record, "correlation_id", None)
        if correlation:
            base = f"{base} [{correlation[:8]}]"
        if record.exc_info:
            base = f"{base}\n{self.formatException(record.exc_info)}"
        return base


def configure(level: str | None = None, json_output: bool | None = None) -> logging.Logger:
    """Configure the package logger once."""
    global _configured
    logger = logging.getLogger(LOGGER_NAME)
    if _configured:
        return logger
    resolved_level = (level or os.getenv("PRINCESSE_LOG_LEVEL") or "INFO").upper()
    if json_output is None:
        json_output = (os.getenv("PRINCESSE_LOG_FORMAT") or "").lower() == "json"
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JsonFormatter() if json_output else TextFormatter())
    logger.handlers = [handler]
    logger.setLevel(getattr(logging, resolved_level, logging.INFO))
    logger.propagate = False
    _configured = True
    return logger


def get_logger(name: str | None = None, correlation_id: str | None = None) -> logging.Logger:
    logger = configure()
    if not name:
        return logger
    child = logger.getChild(name)
    if correlation_id:
        child = logging.LoggerAdapter(child, {"correlation_id": correlation_id})  # type: ignore[assignment]
    return child  # type: ignore[return-value]


def log_exception(logger: logging.Logger, message: str, **fields: Any) -> None:
    """Log a swallowed exception with context instead of discarding it."""
    extra = {"extra_fields": fields} if fields else {}
    logger.error(message, exc_info=True, extra=extra)


def log_swallowed(logger: logging.Logger, message: str, error: BaseException, **fields: Any) -> None:
    extra = {"extra_fields": {**fields, "error": str(error)}}
    logger.warning(message, exc_info=error, extra=extra)
