"""Liveness and readiness probes.

``/health`` answers "is the process alive"; ``/ready`` answers "can this
process serve traffic" by checking the database, object storage and — when the
queue is not running inline — the Celery broker.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import text

from .config import settings
from .database import engine
from .logging_setup import get_logger

logger = get_logger('app.health')


def _check_database() -> dict[str, Any]:
    try:
        with engine.connect() as connection:
            connection.execute(text('SELECT 1'))
        return {'status': 'ok'}
    except Exception as error:  # pragma: no cover - exercised through /ready failure path
        logger.warning('database readiness failed', extra={'error_type': type(error).__name__})
        return {'status': 'error', 'detail': type(error).__name__}


def _check_storage() -> dict[str, Any]:
    from .storage import StorageError, get_storage

    try:
        storage = get_storage()
        storage.healthcheck()
        return {'status': 'ok', 'backend': storage.backend}
    except StorageError as error:
        logger.warning('storage readiness failed', extra={'error_code': error.code})
        return {'status': 'error', 'backend': settings.storage_backend, 'detail': error.code}
    except Exception as error:  # pragma: no cover - defensive
        return {'status': 'error', 'backend': settings.storage_backend, 'detail': type(error).__name__}


def _check_broker() -> dict[str, Any]:
    if settings.eager_queue:
        return {'status': 'skipped', 'mode': 'eager'}
    try:
        from .celery_app import celery

        connection = celery.connection()
        connection.ensure_connection(max_retries=0, timeout=2)
        connection.release()
        return {'status': 'ok', 'mode': 'celery'}
    except Exception as error:
        logger.warning('broker readiness failed', extra={'error_type': type(error).__name__})
        return {'status': 'error', 'mode': 'celery', 'detail': type(error).__name__}


def readiness() -> tuple[bool, dict[str, Any]]:
    checks = {
        'database': _check_database(),
        'storage': _check_storage(),
        'broker': _check_broker(),
    }
    ready = all(check['status'] in {'ok', 'skipped'} for check in checks.values())
    payload = {
        'status': 'ready' if ready else 'not_ready',
        'environment': settings.environment,
        'provider_mode': 'production' if settings.ai_configured else ('demo' if settings.demo_providers_enabled else 'unconfigured'),
        'checks': checks,
    }
    return ready, payload
