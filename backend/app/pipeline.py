"""Worker pipeline: storage → media extraction → AI providers → report.

The pipeline is a plain function so it can be unit tested without a broker.
:mod:`app.tasks` wraps it with Celery retry/idempotency semantics.

Failure policy
--------------
* configuration problems (missing credentials, corrupted media, unknown key)
  are **permanent** – retrying cannot fix them;
* storage/provider/network problems are **transient** – the task retries with
  exponential backoff.
"""
from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from collections.abc import Callable

from sqlalchemy.orm import Session

from . import media as media_module
from .config import settings
from .evidence import redact
from .logging_setup import get_logger, set_job_id
from .models import AnalysisJob, MediaArtifact, Prediction, ProviderCall, Video, VideoAnalysis, VideoSegment
from .providers import (
    AudioAnalysis,
    LLMReport,
    OCRResult,
    ProviderConfigurationError,
    ProviderError,
    Transcript,
    Usage,
    UsageLedger,
    VisionResult,
    assert_report_providers_ready,
    audio_provider,
    llm_report_provider,
    ocr_provider,
    provider_mode,
    resolve_language,
    stt_provider,
    vision_provider,
)
from .reporting import ReportInputs, build_report
from .schemas import VideoContext
from .storage import StorageError, artifact_key, get_storage

logger = get_logger('app.pipeline')


class PipelineCancelled(RuntimeError):
    code = 'cancelled'


class PipelinePermanentError(RuntimeError):
    def __init__(self, message: str, code: str = 'pipeline_failed'):
        super().__init__(message)
        self.code = code


@dataclass
class PipelineResult:
    analysis_id: str
    status: str
    provider_mode: str
    cost_usd: float
    artifacts: int


STAGES = (
    ('queued', 0),
    ('downloading', 10),
    ('media_extraction', 30),
    ('transcribing', 50),
    ('visual_analysis', 65),
    ('scoring', 80),
    ('report_generation', 90),
    ('completed', 100),
)

# Artifact kinds that are uploaded to private storage for later inspection.
UPLOADED_ARTIFACTS = ('audio', 'frame', 'keyframe', 'thumbnail')


def classify_error(error: BaseException) -> tuple[str, bool]:
    """Map an exception onto (error_code, retryable)."""
    if isinstance(error, PipelineCancelled):
        return 'cancelled', False
    if isinstance(error, ProviderConfigurationError):
        return error.code, False
    if isinstance(error, media_module.MediaCorruptedError):
        return error.code, False
    if isinstance(error, media_module.MediaToolUnavailableError):
        return error.code, False
    if isinstance(error, media_module.MediaError):
        return error.code, bool(getattr(error, 'retryable', False))
    if isinstance(error, StorageError):
        return error.code, bool(getattr(error, 'retryable', False))
    if isinstance(error, ProviderError):
        return error.code, bool(getattr(error, 'retryable', False))
    if isinstance(error, PipelinePermanentError):
        return error.code, False
    return 'unexpected_error', True


ProgressCallback = Callable[[str, int], None]


def _noop(_stage: str, _progress: int) -> None:
    return None


def _record_usage(db: Session, analysis_id: str, usage: Usage, status: str = 'ok', error_code: str | None = None) -> None:
    db.add(
        ProviderCall(
            analysis_id=analysis_id,
            kind=usage.kind,
            provider=usage.provider,
            model=usage.model,
            mode=usage.mode,
            status=status,
            attempts=usage.attempts,
            duration_ms=usage.duration_ms,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cost_usd=usage.cost_usd,
            error_code=error_code,
        )
    )


def _optional_provider_call(db: Session, analysis_id: str, kind: str, call):
    """Run an optional provider; a missing credential downgrades the signal."""
    try:
        return call()
    except ProviderConfigurationError as error:
        logger.info('optional provider skipped', extra={'provider_kind': kind, 'error_code': error.code})
        return None
    except ProviderError as error:
        logger.warning('optional provider failed', extra={'provider_kind': kind, 'error_code': error.code})
        db.add(
            ProviderCall(
                analysis_id=analysis_id,
                kind=kind,
                provider=kind,
                model=None,
                mode=provider_mode(),
                status='failed',
                error_code=getattr(error, 'code', 'provider_error'),
            )
        )
        return None


def _store_artifacts(db: Session, video: Video, analysis: VideoAnalysis, bundle: media_module.MediaBundle) -> tuple[int, dict[float, str]]:
    """Upload derived media to private storage and register expiry metadata."""
    storage = get_storage()
    expires_at = datetime.now(timezone.utc) + timedelta(hours=settings.artifact_retention_hours)
    stored = 0
    thumbnail_keys: dict[float, str] = {}

    def register(kind: str, path: Path, timestamp: float | None, content_type: str, extra: dict | None = None) -> str | None:
        nonlocal stored
        if not path.exists():
            return None
        key = artifact_key(video.workspace_id, video.id, kind, path.name)
        result = storage.put_file(path, key, content_type)
        db.add(
            MediaArtifact(
                video_id=video.id,
                analysis_id=analysis.id,
                kind=kind,
                storage_key=result.key,
                content_type=content_type,
                size_bytes=result.size_bytes,
                timestamp_seconds=timestamp,
                artifact_metadata=extra or {},
                expires_at=expires_at,
            )
        )
        stored += 1
        return result.key

    if bundle.audio:
        register('audio', bundle.audio.path, None, 'audio/wav', {'sample_rate': bundle.audio.sample_rate})
    for frame in bundle.frames[: settings.frame_sample_max]:
        register('frame', frame.path, frame.timestamp_seconds, 'image/jpeg')
    for frame in bundle.keyframes[: settings.keyframe_max]:
        register('keyframe', frame.path, frame.timestamp_seconds, 'image/jpeg')
    for frame in bundle.thumbnails:
        key = register('thumbnail', frame.path, frame.timestamp_seconds, 'image/jpeg')
        if key:
            thumbnail_keys[frame.timestamp_seconds] = key
    return stored, thumbnail_keys


def _check_cancelled(db: Session, job: AnalysisJob | None) -> None:
    if job is None:
        return
    db.refresh(job)
    if job.cancel_requested:
        raise PipelineCancelled('Analysis cancelled by the workspace')


def run_analysis_pipeline(db: Session, analysis_id: str, progress: ProgressCallback | None = None) -> PipelineResult:
    """Execute the full production pipeline for one analysis."""
    report_progress = progress or _noop
    analysis = db.get(VideoAnalysis, analysis_id)
    if analysis is None:
        raise PipelinePermanentError(f'Analysis {analysis_id} does not exist', 'analysis_missing')
    video = db.get(Video, analysis.video_id)
    if video is None:
        raise PipelinePermanentError(f'Video for analysis {analysis_id} does not exist', 'video_missing')
    job = db.query(AnalysisJob).filter_by(analysis_id=analysis_id).first()
    set_job_id(job.id if job else analysis_id)

    if analysis.status == 'completed' and analysis.report:
        # Idempotent replay: a redelivered message must not recompute or duplicate.
        return PipelineResult(analysis_id, 'completed', analysis.provider_mode or 'demo', analysis.cost_usd or 0.0, 0)

    _check_cancelled(db, job)
    assert_report_providers_ready()

    saved_context = (analysis.media_metadata or {}).get('context') or {'title': video.original_name, 'account': {}}
    context = VideoContext.model_validate(saved_context)
    language = resolve_language(analysis.language or context.language or context.account.language)
    ledger = UsageLedger()
    mode = provider_mode()

    analysis.started_at = analysis.started_at or datetime.now(timezone.utc)
    analysis.language = language
    analysis.provider_mode = mode
    db.commit()

    workdir = Path(tempfile.mkdtemp(prefix=f'viral-{analysis_id[:8]}-'))
    transcript: Transcript | None = None
    ocr: OCRResult | None = None
    vision: VisionResult | None = None
    audio_result: AudioAnalysis | None = None
    llm: LLMReport | None = None
    bundle: media_module.MediaBundle | None = None
    stored_artifacts = 0
    thumbnail_keys: dict[float, str] = {}

    try:
        # 1. Source media -----------------------------------------------------
        report_progress('downloading', 10)
        analysis.status = 'processing'
        db.commit()
        source = get_storage().download(video.storage_key, workdir / (video.original_name or 'source.mp4'))

        # 2. Measured media pipeline -----------------------------------------
        _check_cancelled(db, job)
        report_progress('media_extraction', 30)
        analysis.status = 'media_extraction'
        db.commit()
        try:
            bundle = media_module.analyze_media(source, workdir / 'artifacts')
        except media_module.MediaToolUnavailableError as error:
            if settings.is_production:
                raise
            logger.warning('media tools unavailable; continuing without measured signals', extra={'error_code': error.code})
            bundle = None

        if bundle is not None:
            probe = bundle.probe
            video.duration_seconds = probe.duration_seconds or video.duration_seconds
            video.width = probe.width or video.width
            video.height = probe.height or video.height
            video.video_codec = probe.video_codec
            video.audio_codec = probe.audio_codec
            video.aspect_ratio = probe.aspect_ratio
            video.fps = probe.fps
            video.has_audio = probe.has_audio
            db.commit()

        # 3. Speech to text ---------------------------------------------------
        _check_cancelled(db, job)
        report_progress('transcribing', 50)
        analysis.status = 'transcribing'
        db.commit()
        if bundle and bundle.audio:
            provider = stt_provider()
            transcript = _optional_provider_call(
                db, analysis.id, 'stt', lambda: provider.transcribe(bundle.audio.path, language)
            )
            if transcript:
                ledger.add(transcript.usage)
                _record_usage(db, analysis.id, transcript.usage)

        # 4. Frame based providers -------------------------------------------
        _check_cancelled(db, job)
        report_progress('visual_analysis', 65)
        analysis.status = 'visual_analysis'
        db.commit()
        frame_paths = [frame.path for frame in (bundle.frames if bundle else [])]
        if frame_paths:
            vision_client = vision_provider()
            vision = _optional_provider_call(
                db, analysis.id, 'vision',
                lambda: vision_client.analyze(frame_paths, 'Assess hook, framing and on-screen text quality.', language),
            )
            if vision:
                ledger.add(vision.usage)
                _record_usage(db, analysis.id, vision.usage)

            ocr_client = ocr_provider()
            ocr = _optional_provider_call(db, analysis.id, 'ocr', lambda: ocr_client.extract(frame_paths, language))
            if ocr:
                ledger.add(ocr.usage)
                _record_usage(db, analysis.id, ocr.usage)

        if bundle and bundle.audio:
            audio_client = audio_provider()
            measured = {
                'silence_seconds': bundle.silence_seconds,
                'speech_ratio': bundle.speech_ratio,
                'duration_seconds': bundle.probe.duration_seconds,
                'transcript': (transcript.text if transcript else '')[:4000],
            }
            audio_result = _optional_provider_call(
                db, analysis.id, 'audio', lambda: audio_client.analyze(bundle.audio.path, measured, language)
            )
            if audio_result:
                ledger.add(audio_result.usage)
                _record_usage(db, analysis.id, audio_result.usage)

        # 5. Persist derived artifacts to private storage ---------------------
        if bundle is not None:
            stored_artifacts, thumbnail_keys = _store_artifacts(db, video, analysis, bundle)
            db.commit()

        # 6. Narrative report --------------------------------------------------
        _check_cancelled(db, job)
        report_progress('scoring', 80)
        analysis.status = 'scoring'
        db.commit()
        llm_payload = {
            'context': context.model_dump(mode='json'),
            'measured_media': bundle.to_metadata() if bundle else None,
            'transcript': transcript.text if transcript else None,
            'on_screen_text': ocr.text if ocr else None,
            'vision': redact(vision.observations) if vision else None,
            'audio': redact(audio_result.metrics) if audio_result else None,
            'language': language,
        }
        llm_client = llm_report_provider()
        try:
            llm = llm_client.generate(llm_payload, language)
        except ProviderConfigurationError:
            if settings.is_production:
                raise
            llm = None
        if llm is not None:
            ledger.add(llm.usage)
            _record_usage(db, analysis.id, llm.usage)
            if llm.usage.mode != 'production':
                llm = None  # demo stub carries no narrative content

        report_progress('report_generation', 90)
        analysis.status = 'report_generation'
        db.commit()
        report = build_report(
            ReportInputs(
                context=context,
                bundle=bundle,
                transcript=transcript,
                ocr=ocr,
                vision=vision,
                audio=audio_result,
                llm=llm,
                usage=ledger,
                provider_mode=mode,
                language=language,
                thumbnail_keys=thumbnail_keys,
            )
        )

        # 7. Persist ------------------------------------------------------------
        analysis.report = report.model_dump(mode='json')
        analysis.media_metadata = {
            'context': context.model_dump(mode='json'),
            **(bundle.to_metadata() if bundle else {'media_analysed': False}),
        }
        analysis.status = 'completed'
        analysis.error = None
        analysis.error_code = None
        analysis.cost_usd = ledger.total_cost_usd
        analysis.completed_at = datetime.now(timezone.utc)
        video.status = 'completed'

        db.query(VideoSegment).filter_by(analysis_id=analysis.id).delete()
        for segment in report.segments:
            db.add(
                VideoSegment(
                    analysis_id=analysis.id,
                    start_seconds=segment.start_time,
                    end_seconds=segment.end_time,
                    kind=segment.title,
                    score=segment.retention_probability,
                    details=segment.model_dump(mode='json'),
                )
            )
        db.query(Prediction).filter_by(video_id=video.id).delete()
        db.add(
            Prediction(
                video_id=video.id,
                predicted_score=report.scores.viral_score,
                predicted_views=report.prediction.expected_views if report.prediction else None,
            )
        )
        db.commit()
        report_progress('completed', 100)
        logger.info(
            'analysis completed',
            extra={
                'analysis_id': analysis.id,
                'provider_mode': mode,
                'cost_usd': ledger.total_cost_usd,
                'artifacts': stored_artifacts,
            },
        )
        return PipelineResult(analysis.id, 'completed', mode, ledger.total_cost_usd, stored_artifacts)
    finally:
        # Temporary working files never outlive the task, success or failure.
        shutil.rmtree(workdir, ignore_errors=True)


def cleanup_expired_artifacts(db: Session, now: datetime | None = None, limit: int = 500) -> int:
    """Delete artifacts whose retention window has passed, in storage and in the DB."""
    moment = now or datetime.now(timezone.utc)
    storage = get_storage()
    stale = (
        db.query(MediaArtifact)
        .filter(MediaArtifact.deleted_at.is_(None), MediaArtifact.expires_at.isnot(None), MediaArtifact.expires_at < moment)
        .limit(limit)
        .all()
    )
    removed = 0
    for artifact in stale:
        try:
            storage.delete(artifact.storage_key)
        except StorageError as error:
            logger.warning('artifact cleanup failed', extra={'error_code': error.code, 'storage_key': artifact.storage_key})
            continue
        artifact.deleted_at = moment
        removed += 1
    db.commit()
    if removed:
        logger.info('expired artifacts removed', extra={'removed': removed})
    return removed


def purge_video_objects(db: Session, video: Video) -> int:
    """Remove every stored object for a video (source + artifacts)."""
    storage = get_storage()
    removed = 0
    for artifact in db.query(MediaArtifact).filter_by(video_id=video.id).all():
        if artifact.deleted_at:
            continue
        try:
            storage.delete(artifact.storage_key)
            artifact.deleted_at = datetime.now(timezone.utc)
            removed += 1
        except StorageError:
            continue
    try:
        storage.delete(video.storage_key)
        removed += 1
    except StorageError:
        pass
    db.commit()
    return removed
