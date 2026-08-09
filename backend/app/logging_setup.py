"""Structured JSON logging and request correlation.

Every log line is a single JSON object so that a log shipper can index it
without regex parsing. The active request id is stored in a context variable
so API handlers, Celery tasks and provider adapters all emit the same
correlation id without threading it through every function signature.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any

from .config import settings

_request_id: ContextVar[str | None] = ContextVar('request_id', default=None)
_job_id: ContextVar[str | None] = ContextVar('job_id', default=None)

# Never let these keys reach a log sink, even if a caller passes them as extra.
REDACTED_KEYS = {
    'authorization', 'api_key', 'apikey', 'openai_api_key', 'secret', 'password',
    'token', 'access_key', 'secret_key', 'encryption_key', 'jwt_secret', 'signature',
    'raw_response', 'raw_event', 'audio', 'image', 'b64_json', 'data',
}

_RESERVED = {
    'args', 'asctime', 'created', 'exc_info', 'exc_text', 'filename', 'funcName',
    'levelname', 'levelno', 'lineno', 'module', 'msecs', 'message', 'msg', 'name',
    'pathname', 'process', 'processName', 'relativeCreated', 'stack_info',
    'thread', 'threadName', 'taskName',
}


def new_request_id() -> str:
    return uuid.uuid4().hex


def set_request_id(value: str | None) -> str:
    value = value or new_request_id()
    _request_id.set(value)
    return value


def get_request_id() -> str | None:
    return _request_id.get()


def set_job_id(value: str | None) -> None:
    _job_id.set(value)


def get_job_id() -> str | None:
    return _job_id.get()


def scrub(value: Any, _depth: int = 0) -> Any:
    """Recursively drop credential-ish and payload-ish values from log records."""
    if _depth > 4:
        return '[truncated]'
    if isinstance(value, dict):
        return {
            key: ('[redacted]' if str(key).lower() in REDACTED_KEYS else scrub(item, _depth + 1))
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [scrub(item, _depth + 1) for item in value[:20]]
    if isinstance(value, (bytes, bytearray)):
        return f'[{len(value)} bytes]'
    if isinstance(value, str) and len(value) > 2000:
        return value[:2000] + '…[truncated]'
    return value


class JsonFormatter(logging.Formatter):
    """Render a log record as one JSON line."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            'timestamp': datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'service': settings.app_name,
            'environment': settings.environment,
        }
        request_id = get_request_id()
        if request_id:
            payload['request_id'] = request_id
        job_id = get_job_id()
        if job_id:
            payload['job_id'] = job_id
        for key, value in record.__dict__.items():
            if key in _RESERVED or key.startswith('_') or key in payload:
                continue
            # A sensitive *field name* is redacted even at the top level, so
            # ``logger.info(..., extra={'api_key': ...})`` cannot leak.
            payload[key] = '[redacted]' if str(key).lower() in REDACTED_KEYS else scrub(value)
        if record.exc_info:
            payload['exception'] = self.formatException(record.exc_info)[-4000:]
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(level: str | None = None, force: bool = False) -> None:
    """Install the JSON handler on the root logger exactly once."""
    root = logging.getLogger()
    if getattr(root, '_viral_json_logging', False) and not force:
        return
    handler = logging.StreamHandler(sys.stdout)
    if settings.log_format == 'json':
        handler.setFormatter(JsonFormatter())
    else:  # human readable local development
        handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(name)s %(message)s'))
    root.handlers = [handler]
    root.setLevel(level or os.getenv('LOG_LEVEL', settings.log_level))
    for noisy in ('uvicorn.access', 'botocore', 'boto3', 'urllib3', 's3transfer', 'httpx', 'httpcore'):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    root._viral_json_logging = True  # type: ignore[attr-defined]


def get_logger(name: str) -> logging.Logger:
    configure_logging()
    return logging.getLogger(name)
