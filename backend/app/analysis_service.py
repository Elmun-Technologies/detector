"""Analysis job service: idempotent enqueue, cancel, retry and progress.

Routes stay thin; the queue semantics live here so the HTTP layer, the Telegram
bot and the recovery task all behave identically.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from .config import settings
from .logging_setup import get_logger
from .models import AnalysisJob, Video, VideoAnalysis
from .schemas import JobProgress, VideoContext

logger = get_logger('app.analysis')

ACTIVE_STATUSES = {'queued', 'running', 'retrying'}
TERMINAL_STATUSES = {'completed', 'failed', 'cancelled'}


class DispatchError(RuntimeError):
    """The job is persisted but the broker refused/failed to accept it."""

    code = 'broker_unavailable'


def build_idempotency_key(workspace_id: str, checksum: str | None, provided: str | None) -> str:
    """Client key when supplied, otherwise a deterministic content key."""
    if provided:
        return f'{workspace_id}:{provided[:96]}'
    digest = checksum or datetime.now(timezone.utc).isoformat()
    return f'{workspace_id}:{hashlib.sha256(digest.encode()).hexdigest()[:48]}'


def find_job_by_key(db: Session, idempotency_key: str) -> AnalysisJob | None:
    return db.query(AnalysisJob).filter_by(idempotency_key=idempotency_key).first()


def create_analysis(db: Session, video: Video, context: VideoContext, idempotency_key: str) -> tuple[VideoAnalysis, AnalysisJob]:
    analysis = VideoAnalysis(
        video_id=video.id,
        status='queued',
        language=context.language or context.account.language,
        media_metadata={'context': context.model_dump(mode='json')},
    )
    db.add(analysis)
    db.flush()
    job = AnalysisJob(
        analysis_id=analysis.id,
        status='queued',
        stage='queued',
        progress=0,
        max_attempts=settings.task_max_retries,
        idempotency_key=idempotency_key,
    )
    db.add(job)
    db.flush()
    return analysis, job


def dispatch(db: Session, job: AnalysisJob) -> AnalysisJob:
    """Hand the job to the worker. The API never runs the pipeline itself.

    The job row is already committed, so a broker outage never loses work: the
    row stays ``queued`` and :func:`app.tasks.recover_stuck_jobs` re-dispatches
    it once the broker is back.
    """
    from .tasks import analyze_video

    try:
        async_result = analyze_video.delay(job.analysis_id, job.idempotency_key)
    except Exception as error:  # broker down / connection refused
        job.status = 'queued'
        job.error_code = 'broker_unavailable'
        job.error = str(error)[:500]
        db.commit()
        logger.error(
            'analysis dispatch failed',
            extra={'analysis_id': job.analysis_id, 'error_code': 'broker_unavailable'},
        )
        raise DispatchError('Task broker is unavailable') from error
    job.task_id = getattr(async_result, 'id', None)
    db.commit()
    logger.info(
        'analysis dispatched',
        extra={'analysis_id': job.analysis_id, 'task_id': job.task_id, 'queue_mode': settings.queue_mode},
    )
    return job


def request_cancel(db: Session, analysis_id: str) -> AnalysisJob | None:
    job = db.query(AnalysisJob).filter_by(analysis_id=analysis_id).first()
    analysis = db.get(VideoAnalysis, analysis_id)
    if job is None:
        return None
    job.cancel_requested = True
    if job.status in {'queued', 'retrying'}:
        job.status = 'cancelled'
        job.finished_at = datetime.now(timezone.utc)
        if analysis is not None:
            analysis.status = 'cancelled'
    db.commit()
    logger.info('analysis cancel requested', extra={'analysis_id': analysis_id, 'job_status': job.status})
    return job


def request_retry(db: Session, analysis_id: str) -> AnalysisJob | None:
    """Reset a terminal job and re-dispatch it."""
    job = db.query(AnalysisJob).filter_by(analysis_id=analysis_id).first()
    analysis = db.get(VideoAnalysis, analysis_id)
    if job is None or analysis is None:
        return None
    if job.status in ACTIVE_STATUSES:
        return job
    job.status = 'queued'
    job.stage = 'queued'
    job.progress = 0
    job.attempts = 0
    job.cancel_requested = False
    job.error = None
    job.error_code = None
    job.finished_at = None
    job.next_retry_at = None
    analysis.status = 'queued'
    analysis.error = None
    analysis.error_code = None
    db.commit()
    return dispatch(db, job)


def progress_for(db: Session, analysis_id: str) -> JobProgress | None:
    analysis = db.get(VideoAnalysis, analysis_id)
    if analysis is None:
        return None
    job = db.query(AnalysisJob).filter_by(analysis_id=analysis_id).first()
    if job is None:
        return JobProgress(
            analysis_id=analysis_id,
            job_id='',
            status=analysis.status,
            progress=100 if analysis.status == 'completed' else 0,
            updated_at=analysis.updated_at,
        )
    return JobProgress(
        analysis_id=analysis_id,
        job_id=job.id,
        status=job.status,
        stage=job.stage,
        progress=job.progress or (100 if job.status == 'completed' else 0),
        attempts=job.attempts,
        max_attempts=job.max_attempts,
        error_code=job.error_code,
        error=job.error,
        cancel_requested=job.cancel_requested,
        updated_at=job.updated_at,
    )
