"""Logging configuration helpers."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict

from .config import Settings


class JsonLogFormatter(logging.Formatter):
    """A simple JSON formatter for structured logging output."""

    def format(self, record: logging.LogRecord) -> str:  # pragma: no cover - formatting logic
        payload: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = self.formatStack(record.stack_info)
        extra = {
            key: value
            for key, value in record.__dict__.items()
            if key not in logging.LogRecord.__slots__ and key not in {
                "args",
                "name",
                "msg",
                "levelname",
                "levelno",
                "pathname",
                "filename",
                "module",
                "exc_info",
                "exc_text",
                "stack_info",
                "lineno",
                "funcName",
                "created",
                "msecs",
                "relativeCreated",
                "thread",
                "threadName",
                "processName",
                "process",
            }
        }
        if extra:
            payload.update(_serialise_extra(extra))
        return json.dumps(payload, default=_stringify)


def _stringify(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (list, tuple)):
        return [_stringify(item) for item in value]
    if isinstance(value, dict):
        return {key: _stringify(item) for key, item in value.items()}
    return repr(value)


def _serialise_extra(extra: Dict[str, Any]) -> Dict[str, Any]:
    return {key: _stringify(value) for key, value in extra.items()}


def configure_logging(settings: Settings) -> None:
    """Configure root logging based on the provided settings."""

    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    root_logger = logging.getLogger()
    if getattr(configure_logging, "_configured", False):
        root_logger.setLevel(level)
        return

    handler = logging.StreamHandler()
    handler.setFormatter(JsonLogFormatter())
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(level)
    configure_logging._configured = True  # type: ignore[attr-defined]


__all__ = ["configure_logging", "JsonLogFormatter"]
