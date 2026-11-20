"""Structured JSON logging with recursive redaction of secrets and personal data (research R12)."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

REDACTED = "[REDACTED]"
_SENSITIVE_EXACT = {"authorization", "password", "cpf", "idtoken", "code", "state", "secret"}
_SENSITIVE_PARTS = ("token", "secret", "password")
_STANDARD_ATTRS = set(vars(logging.makeLogRecord({}))) | {"message", "asctime", "taskName"}
# Bearer values and long opaque strings that look like tokens inside free-text messages.
_BEARER_RE = re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]+")


def is_sensitive_key(key: str) -> bool:
    lowered = key.lower().replace("-", "").replace("_", "")
    return lowered in _SENSITIVE_EXACT or any(part in lowered for part in _SENSITIVE_PARTS)


def redact(value: Any) -> Any:
    """Return a copy of ``value`` with sensitive keys replaced, recursing into containers."""
    if isinstance(value, Mapping):
        return {
            k: (REDACTED if isinstance(k, str) and is_sensitive_key(k) else redact(v))
            for k, v in value.items()
        }
    if isinstance(value, list | tuple):
        return [redact(v) for v in value]
    if isinstance(value, str):
        return _BEARER_RE.sub("Bearer " + REDACTED, value)
    return value


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": redact(record.getMessage()),
        }
        extras = {k: v for k, v in vars(record).items() if k not in _STANDARD_ATTRS}
        payload.update(redact(extras))
        if record.exc_info and record.exc_info[0] is not None:
            payload["exc_type"] = record.exc_info[0].__name__
        return json.dumps(payload, default=str)


class _AccessLogFilter(logging.Filter):
    """Strip query strings from uvicorn access logs (OAuth ``code``/``state`` travel there)."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple) and len(record.args) >= 3:
            args = list(record.args)
            if isinstance(args[2], str):
                args[2] = args[2].split("?", 1)[0]
            record.args = tuple(args)
        return True


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers[:] = []
        lg.propagate = True
    logging.getLogger("uvicorn.access").addFilter(_AccessLogFilter())
    # httpx logs full URLs at INFO; keep it at WARNING.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpx2").setLevel(logging.WARNING)
