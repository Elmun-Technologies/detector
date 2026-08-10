"""Celery tasks: analysis execution, retry policy, recovery and cleanup."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from celery.exceptions import Ignore, SoftTimeLimitExceeded

from .celery_app import celery
from .config import settings
from .database import SessionLocal
from .logging_setup import get_logger, set_job_id
from .models import AnalysisJob, VideoAnalysis
from .pipeline import (
    PipelineCancelled,
    classify_error,
    cleanup_expired_artifacts as cleanup_artifacts,
    run_analysis_pipeline,
)

logger = get_logger('app.tasks')

TERMINAL_STATUSES = {'completed', 'failed', 'cancelled'}


def retry_countdown(attempt: int) -> int:
    """Exponential backoff, capped, so a broken provider is not hammered."""
    base = max(1, settings.task_retry_backoff_seconds)
    return int(min(base * (2 ** max(0, attempt - 1)), settings.task_retry_backoff_max_seconds))


def should_retry(retryable: bool, attempts: int, max_attempts: int) -> bool:
    return retryable and attempts < max_attempts


def _finish(db, job: AnalysisJob | None, analysis: VideoAnalysis | None, status: str, *, code: str | None = None, message: str | None = None) -> None:
    moment = datetime.now(timezone.utc)
    if job is not None:
        job.status = status
        job.error_code = code
        job.error = message
        job.finished_at = moment
        job.progress = 100 if status == 'completed' else job.progress
    if analysis is not None and status != 'completed':
        analysis.status = 'cancelled' if status == 'cancelled' else 'failed'
        analysis.error_code = code
        analysis.error = message
    db.commit()


@celery.task(
    bind=True,
    name='app.tasks.analyze_video',
    acks_late=True,
    max_retries=settings.task_max_retries,
    soft_time_limit=settings.task_soft_time_limit,
    time_limit=settings.task_time_limit,
)
def analyze_video(self, analysis_id: str, idempotency_key: str | None = None):
    """Run one analysis. Safe to redeliver: completed work is never redone."""
    db = SessionLocal()
    job: AnalysisJob | None = None
    analysis: VideoAnalysis | None = None
    try:
        analysis = db.get(VideoAnalysis, analysis_id)
        if analysis is None:
            logger.warning('analysis missing', extra={'analysis_id': analysis_id})
            return {'analysis_id': analysis_id, 'status': 'missing'}
        job = db.query(AnalysisJob).filter_by(analysis_id=analysis_id).first()
        set_job_id(job.id if job else analysis_id)

        if job is not None and job.status == 'completed' and analysis.status == 'completed':
            return {'analysis_id': analysis_id, 'status': 'completed', 'idempotent': True}
        if job is not None and job.cancel_requested:
            _finish(db, job, analysis, 'cancelled', code='cancelled', message='Cancelled before execution')
            return {'analysis_id': analysis_id, 'status': 'cancelled'}

        if job is not None:
            job.status = 'running'
            job.stage = 'queued'
            job.progress = 0
            job.attempts += 1
            job.task_id = self.request.id
            job.locked_at = datetime.now(timezone.utc)
            job.heartbeat_at = datetime.now(timezone.utc)
            job.error = None
            job.error_code = None
            if idempotency_key and not job.idempotency_key:
                job.idempotency_key = idempotency_key
            db.commit()

        def progress(stage: str, percent: int) -> None:
            if job is None:
                return
            job.stage = stage
            job.progress = percent
            job.heartbeat_at = datetime.now(timezone.utc)
            db.commit()

        result = run_analysis_pipeline(db, analysis_id, progress)
        _finish(db, job, analysis, 'completed')
        return {
            'analysis_id': analysis_id,
            'status': result.status,
            'provider_mode': result.provider_mode,
            'cost_usd': result.cost_usd,
            'artifacts': result.artifacts,
        }
    except PipelineCancelled as error:
        _finish(db, job, analysis, 'cancelled', code='cancelled', message=str(error))
        return {'analysis_id': analysis_id, 'status': 'cancelled'}
    except SoftTimeLimitExceeded as error:
        _finish(db, job, analysis, 'failed', code='task_timeout', message='Worker soft time limit exceeded')
        logger.error('analysis timed out', extra={'analysis_id': analysis_id})
        raise error
    except Exception as error:
        code, retryable = classify_error(error)
        attempts = job.attempts if job else self.request.retries + 1
        max_attempts = (job.max_attempts if job else settings.task_max_retries) or settings.task_max_retries
        logger.error(
            'analysis failed',
            extra={'analysis_id': analysis_id, 'error_code': code, 'attempts': attempts, 'retryable': retryable},
        )
        if should_retry(retryable, attempts, max_attempts):
            countdown = retry_countdown(attempts)
            if job is not None:
                job.status = 'retrying'
                job.error_code = code
                job.error = str(error)[:500]
                job.next_retry_at = datetime.now(timezone.utc) + timedelta(seconds=countdown)
                db.commit()
            if analysis is not None:
                analysis.status = 'queued'
                analysis.error_code = code
                db.commit()
            raise self.retry(exc=error, countdown=countdown, max_retries=max_attempts) from error
        _finish(db, job, analysis, 'failed', code=code, message=str(error)[:500])
        raise
    finally:
        db.close()


@celery.task(name='app.tasks.recover_stuck_jobs')
def recover_stuck_jobs(timeout_seconds: int | None = None) -> int:
    """Requeue jobs whose worker died without releasing them.

    A job is considered abandoned when it is still ``running``/``retrying`` and
    its heartbeat is older than ``JOB_HEARTBEAT_TIMEOUT_SECONDS``.
    """
    limit = timeout_seconds or settings.job_heartbeat_timeout_seconds
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=limit)
    db = SessionLocal()
    recovered = 0
    try:
        candidates = (
            db.query(AnalysisJob)
            .filter(AnalysisJob.status.in_(['running', 'retrying', 'queued']))
            .all()
        )
        for job in candidates:
            if job.status == 'queued' and job.task_id:
                # Accepted by the broker; the worker owns it now.
                continue
            heartbeat = job.heartbeat_at or job.locked_at or job.updated_at
            if heartbeat is not None and heartbeat.tzinfo is None:
                heartbeat = heartbeat.replace(tzinfo=timezone.utc)
            if heartbeat is not None and heartbeat > cutoff:
                continue
            if job.cancel_requested:
                job.status = 'cancelled'
                job.finished_at = datetime.now(timezone.utc)
                continue
            if job.attempts >= (job.max_attempts or settings.task_max_retries):
                job.status = 'failed'
                job.error_code = 'worker_lost'
                job.error = 'Worker did not finish the job and the retry budget is exhausted'
                job.finished_at = datetime.now(timezone.utc)
                analysis = db.get(VideoAnalysis, job.analysis_id)
                if analysis is not None:
                    analysis.status = 'failed'
                    analysis.error_code = 'worker_lost'
                continue
            job.status = 'queued'
            job.stage = 'queued'
            job.error_code = 'worker_lost'
            job.heartbeat_at = None
            db.commit()
            analyze_video.delay(job.analysis_id, job.idempotency_key)
            recovered += 1
        db.commit()
        return recovered
    finally:
        db.close()


@celery.task(name='app.tasks.cleanup_expired_artifacts')
def cleanup_expired_artifacts() -> int:
    """Delete temporary media artifacts whose retention window has expired."""
    db = SessionLocal()
    try:
        return cleanup_artifacts(db)
    finally:
        db.close()


__all__ = [
    'analyze_video',
    'recover_stuck_jobs',
    'cleanup_expired_artifacts',
    'retry_countdown',
    'should_retry',
    'Ignore',
]
