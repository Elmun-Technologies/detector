"""Celery application.

The API process and the worker process share this module but never share a
role: the API only ever calls ``.delay()``/``.apply_async()``, all media and
provider work happens in the worker. Eager (inline) execution is a development
and test affordance and is refused in production.
"""
from __future__ import annotations

import os

from celery import Celery
from celery.signals import setup_logging, worker_ready

from .config import settings
from .logging_setup import configure_logging, get_logger

logger = get_logger('app.celery')


def _eager_requested() -> bool:
    env_flag = (os.getenv('CELERY_TASK_ALWAYS_EAGER', '') or '').lower() in {'1', 'true', 'yes'}
    return env_flag or settings.queue_mode in {'inline', 'eager'}


def build_celery() -> Celery:
    if settings.is_production and _eager_requested():
        raise RuntimeError(
            'Production configuration error: QUEUE_MODE/CELERY_TASK_ALWAYS_EAGER request inline execution. '
            'Production must run a separate Celery worker against Redis.'
        )

    app = Celery('viral_video_ai', broker=settings.broker_url, backend=settings.result_backend)
    app.conf.update(
        task_serializer='json',
        result_serializer='json',
        accept_content=['json'],
        timezone='UTC',
        enable_utc=True,
        task_track_started=True,
        task_default_queue='analysis',
        task_routes={'app.tasks.*': {'queue': 'analysis'}},
        # Deliver-once semantics are impossible; make redelivery safe instead.
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        worker_prefetch_multiplier=1,
        worker_max_tasks_per_child=50,
        task_soft_time_limit=settings.task_soft_time_limit,
        task_time_limit=settings.task_time_limit,
        result_expires=86400,
        broker_transport_options={
            'visibility_timeout': max(3600, settings.task_time_limit * 2),
            'max_retries': 3,
        },
        broker_connection_retry_on_startup=True,
        task_always_eager=settings.eager_queue or _eager_requested(),
        # Inline execution must behave like a worker: a failing task marks the
        # job failed, it never explodes the HTTP request that enqueued it.
        # (It also lets Celery re-execute eager retries instead of raising.)
        task_eager_propagates=False,
        beat_schedule={
            'recover-stuck-analysis-jobs': {
                'task': 'app.tasks.recover_stuck_jobs',
                'schedule': 60.0,
            },
            'cleanup-expired-media-artifacts': {
                'task': 'app.tasks.cleanup_expired_artifacts',
                'schedule': 900.0,
            },
        },
    )
    return app


celery = build_celery()


@setup_logging.connect
def _configure_worker_logging(**_kwargs):  # pragma: no cover - celery bootstrap
    configure_logging(force=True)


@worker_ready.connect
def _recover_on_boot(**_kwargs):  # pragma: no cover - requires a live worker
    """Re-queue jobs abandoned by a worker that died mid-task."""
    from .tasks import recover_stuck_jobs

    try:
        recovered = recover_stuck_jobs()
        logger.info('worker recovery scan complete', extra={'recovered': recovered})
    except Exception:
        logger.exception('worker recovery scan failed')
