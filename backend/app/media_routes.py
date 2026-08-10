"""Milestone 2 media API: presigned uploads, job control and artifact access.

Every route is workspace-scoped through the RBAC resolver. Responses never
contain raw provider payloads, credentials or absolute filesystem paths — only
storage keys and short-lived signed URLs.
"""
from __future__ import annotations

import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from . import analysis_service
from .auth import identity, require_workspace
from .config import settings
from .database import get_db
from .evidence import redact
from .limits import assert_video_limit
from .logging_setup import get_logger
from .models import AuditLog, MediaArtifact, Video, VideoAnalysis, Workspace
from .rbac import authorize_resource
from .schemas import JobProgress, VideoContext
from .security import hash_ip, rate_limit
from .storage import (
    LocalStorage,
    StorageError,
    StorageNotFoundError,
    get_storage,
    safe_filename,
    source_key,
)
from .video import ALLOWED_CONTENT_TYPES, ALLOWED_SUFFIXES, VideoValidationError, validate_upload

logger = get_logger('app.media_routes')
router = APIRouter(prefix='/v1', dependencies=[Depends(rate_limit)])


class PresignRequest(BaseModel):
    filename: str = Field(max_length=255)
    content_type: str = Field(default='video/mp4', max_length=100)
    size_bytes: int = Field(gt=0)


class PresignResponse(BaseModel):
    video_id: str
    storage_key: str
    upload_url: str
    method: str
    headers: dict[str, str]
    expires_at: datetime
    max_bytes: int


class CompleteUploadRequest(BaseModel):
    context: VideoContext = Field(default_factory=VideoContext)
    idempotency_key: str | None = Field(default=None, max_length=96)


def _audit(db: Session, request: Request, workspace_id: str | None, action: str, target_type: str, target_id: str | None, user_id: str | None = None) -> None:
    db.add(
        AuditLog(
            workspace_id=workspace_id,
            user_id=user_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            ip_hash=hash_ip(request.client.host if request.client else None),
        )
    )


@router.post('/workspaces/{workspace_id}/videos/presign-upload', response_model=PresignResponse, status_code=201)
def presign_upload(
    workspace_id: str,
    payload: PresignRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: str = Depends(identity),
) -> PresignResponse:
    """Reserve a private object key and return a short-lived upload URL."""
    require_workspace(db, workspace_id, user, 'editor')
    workspace = db.get(Workspace, workspace_id)
    if workspace is None:
        raise HTTPException(404, 'Workspace not found')
    try:
        assert_video_limit(db, workspace_id, workspace.plan)
    except PermissionError as error:
        raise HTTPException(429, str(error)) from error

    name = safe_filename(payload.filename)
    if Path(name).suffix.lower() not in ALLOWED_SUFFIXES:
        raise HTTPException(422, 'Faqat MP4, MOV yoki AVI video qabul qilinadi.')
    if payload.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(422, 'Faylning Content-Type qiymati video formatiga mos emas.')
    if payload.size_bytes > settings.max_upload_bytes:
        raise HTTPException(413, f'Fayl hajmi {settings.max_upload_bytes // (1024 * 1024)} MB limitdan oshgan.')

    video = Video(
        workspace_id=workspace_id,
        storage_key='pending',
        original_name=name,
        content_type=payload.content_type,
        size_bytes=payload.size_bytes,
        status='awaiting_upload',
        storage_backend=settings.storage_backend,
    )
    db.add(video)
    db.flush()
    key = source_key(workspace_id, video.id, name)
    video.storage_key = key
    try:
        presigned = get_storage().presigned_put_url(key, content_type=payload.content_type)
    except StorageError as error:
        raise HTTPException(503, f'Storage unavailable: {error.code}') from error
    _audit(db, request, workspace_id, 'video.upload_presigned', 'video', video.id, user)
    db.commit()
    return PresignResponse(
        video_id=video.id,
        storage_key=key,
        upload_url=presigned.url,
        method=presigned.method,
        headers=presigned.headers,
        expires_at=presigned.expires_at,
        max_bytes=settings.max_upload_bytes,
    )


@router.post('/workspaces/{workspace_id}/videos/{video_id}/complete-upload', status_code=202)
def complete_upload(
    workspace_id: str,
    video_id: str,
    payload: CompleteUploadRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: str = Depends(identity),
    idempotency_key: str | None = Header(default=None, alias='Idempotency-Key'),
):
    """Confirm a presigned upload, then queue the analysis exactly once."""
    require_workspace(db, workspace_id, user, 'editor')
    video = db.get(Video, video_id)
    if video is None or video.workspace_id != workspace_id:
        raise HTTPException(404, 'Video not found')

    storage = get_storage()
    try:
        stat = storage.stat(video.storage_key)
    except StorageNotFoundError as error:
        raise HTTPException(409, 'Uploaded object was not found in storage') from error
    except StorageError as error:
        raise HTTPException(503, f'Storage unavailable: {error.code}') from error

    try:
        validate_upload(video.original_name, video.content_type, stat.size_bytes)
    except VideoValidationError as error:
        raise HTTPException(422, str(error)) from error

    video.size_bytes = stat.size_bytes
    if video.status in {'awaiting_upload', 'uploaded', 'failed'}:
        # A replayed confirmation must never push a finished video back to queued.
        video.status = 'queued'

    key = analysis_service.build_idempotency_key(workspace_id, video.checksum_sha256 or video.storage_key, payload.idempotency_key or idempotency_key)
    existing = analysis_service.find_job_by_key(db, key)
    if existing is not None:
        db.commit()
        return {'video_id': video.id, 'analysis_id': existing.analysis_id, 'status': existing.status, 'idempotent': True}

    analysis, job = analysis_service.create_analysis(db, video, payload.context, key)
    _audit(db, request, workspace_id, 'video.uploaded', 'video', video.id, user)
    db.commit()
    try:
        analysis_service.dispatch(db, job)
    except analysis_service.DispatchError as error:
        raise HTTPException(
            503,
            {
                'code': 'broker_unavailable',
                'message': 'Navbat vaqtincha ishlamayapti; tahlil avtomatik qayta navbatga olinadi.',
                'video_id': video.id,
                'analysis_id': analysis.id,
            },
        ) from error
    return {'video_id': video.id, 'analysis_id': analysis.id, 'status': 'queued', 'idempotent': False}


@router.get('/analyses/{analysis_id}/progress', response_model=JobProgress)
def analysis_progress(analysis_id: str, db: Session = Depends(get_db), user: str = Depends(identity)) -> JobProgress:
    authorize_resource(db, 'analysis', analysis_id, user, 'viewer')
    progress = analysis_service.progress_for(db, analysis_id)
    if progress is None:
        raise HTTPException(404, 'Analysis not found')
    return progress


@router.post('/analyses/{analysis_id}/cancel')
def cancel_analysis(analysis_id: str, request: Request, db: Session = Depends(get_db), user: str = Depends(identity)):
    workspace_id = authorize_resource(db, 'analysis', analysis_id, user, 'editor')
    job = analysis_service.request_cancel(db, analysis_id)
    if job is None:
        raise HTTPException(404, 'Analysis job not found')
    _audit(db, request, workspace_id, 'analysis.cancel_requested', 'analysis', analysis_id, user)
    db.commit()
    return {'analysis_id': analysis_id, 'status': job.status, 'cancel_requested': job.cancel_requested}


@router.post('/analyses/{analysis_id}/retry', status_code=202)
def retry_analysis(analysis_id: str, request: Request, db: Session = Depends(get_db), user: str = Depends(identity)):
    workspace_id = authorize_resource(db, 'analysis', analysis_id, user, 'editor')
    try:
        job = analysis_service.request_retry(db, analysis_id)
    except analysis_service.DispatchError as error:
        raise HTTPException(503, {'code': 'broker_unavailable', 'analysis_id': analysis_id}) from error
    if job is None:
        raise HTTPException(404, 'Analysis job not found')
    _audit(db, request, workspace_id, 'analysis.retried', 'analysis', analysis_id, user)
    db.commit()
    return {'analysis_id': analysis_id, 'status': job.status, 'attempts': job.attempts}


@router.get('/videos/{video_id}/artifacts')
def list_artifacts(video_id: str, db: Session = Depends(get_db), user: str = Depends(identity)):
    """List derived media artifacts with short-lived download URLs."""
    authorize_resource(db, 'video', video_id, user, 'viewer')
    storage = get_storage()
    items = []
    for artifact in db.query(MediaArtifact).filter_by(video_id=video_id).order_by(MediaArtifact.kind).all():
        if artifact.deleted_at:
            continue
        entry = {
            'id': artifact.id,
            'kind': artifact.kind,
            'storage_key': artifact.storage_key,
            'content_type': artifact.content_type,
            'size_bytes': artifact.size_bytes,
            'timestamp_seconds': artifact.timestamp_seconds,
            'expires_at': artifact.expires_at,
            'metadata': redact(artifact.artifact_metadata or {}),
        }
        try:
            entry['download_url'] = storage.presigned_get_url(artifact.storage_key).url
        except StorageError as error:
            entry['download_url'] = None
            entry['error_code'] = error.code
        items.append(entry)
    return {'video_id': video_id, 'artifacts': items}


@router.get('/videos/{video_id}/source-url')
def source_download_url(video_id: str, db: Session = Depends(get_db), user: str = Depends(identity)):
    """Short-lived private download URL for the original upload."""
    authorize_resource(db, 'video', video_id, user, 'editor')
    video = db.get(Video, video_id)
    if video is None:
        raise HTTPException(404, 'Video not found')
    try:
        presigned = get_storage().presigned_get_url(video.storage_key)
    except StorageError as error:
        raise HTTPException(503, f'Storage unavailable: {error.code}') from error
    return {'url': presigned.url, 'expires_at': presigned.expires_at, 'method': presigned.method}


# --------------------------------------------------------------------------- local signed object endpoint
def _local_backend(key: str, method: str, expires: int, signature: str) -> LocalStorage:
    """Resolve + authorise the local storage backend for a signed object URL.

    In production the presigned URL points straight at S3/MinIO, so these two
    routes are disabled and no application process ever streams private media.
    """
    if settings.storage_backend != 'local':
        raise HTTPException(404, 'Signed object endpoint is only used by the local storage backend')
    storage = get_storage()
    if not isinstance(storage, LocalStorage):  # pragma: no cover - defensive
        raise HTTPException(404, 'Local storage backend is not active')
    try:
        LocalStorage.verify(key, method, expires, signature)
    except StorageError as error:
        raise HTTPException(403, error.code) from error
    return storage


@router.put('/storage/objects/{key:path}', include_in_schema=False)
async def local_signed_object_put(key: str, request: Request, expires: int = 0, signature: str = ''):
    """Accept a presigned upload for the local development storage backend."""
    storage = _local_backend(key, 'PUT', expires, signature)
    body = await request.body()
    if len(body) > settings.max_upload_bytes:
        raise HTTPException(413, 'File too large')
    with tempfile.NamedTemporaryFile(delete=False) as handle:
        handle.write(body)
        temporary = Path(handle.name)
    try:
        stored = storage.put_file(temporary, key, request.headers.get('content-type'))
    finally:
        temporary.unlink(missing_ok=True)
    return {'key': stored.key, 'size_bytes': stored.size_bytes}


@router.get('/storage/objects/{key:path}', include_in_schema=False)
async def local_signed_object_get(key: str, expires: int = 0, signature: str = ''):
    """Serve a private object for the local development storage backend."""
    storage = _local_backend(key, 'GET', expires, signature)
    try:
        stat = storage.stat(key)
    except StorageNotFoundError as error:
        raise HTTPException(404, 'Object not found') from error
    path = storage._path(key)  # noqa: SLF001 - local adapter internal by design
    return FileResponse(
        path,
        media_type='application/octet-stream',
        headers={
            'Content-Length': str(stat.size_bytes),
            'Cache-Control': 'private, no-store',
            'X-Object-Expires': (datetime.now(timezone.utc) + timedelta(seconds=settings.storage_url_ttl_seconds)).isoformat(),
        },
    )


@router.get('/analyses/{analysis_id}/provider-usage')
def provider_usage(analysis_id: str, db: Session = Depends(get_db), user: str = Depends(identity)):
    """Cost/latency ledger for an analysis (no raw provider payloads)."""
    authorize_resource(db, 'analysis', analysis_id, user, 'admin')
    analysis = db.get(VideoAnalysis, analysis_id)
    if analysis is None:
        raise HTTPException(404, 'Analysis not found')
    from .models import ProviderCall

    calls = db.query(ProviderCall).filter_by(analysis_id=analysis_id).all()
    return {
        'analysis_id': analysis_id,
        'provider_mode': analysis.provider_mode,
        'total_cost_usd': analysis.cost_usd or 0.0,
        'calls': [
            {
                'kind': call.kind,
                'provider': call.provider,
                'model': call.model,
                'mode': call.mode,
                'status': call.status,
                'attempts': call.attempts,
                'duration_ms': call.duration_ms,
                'input_tokens': call.input_tokens,
                'output_tokens': call.output_tokens,
                'cost_usd': call.cost_usd,
                'error_code': call.error_code,
            }
            for call in calls
        ],
    }


@router.get('/system/storage', include_in_schema=False)
def storage_status(response: Response, db: Session = Depends(get_db), user: str = Depends(identity)):
    """Operational check used by dashboards; requires an authenticated user."""
    try:
        storage = get_storage()
        storage.healthcheck()
        return {'backend': storage.backend, 'status': 'ok'}
    except StorageError as error:
        response.status_code = 503
        return {'backend': settings.storage_backend, 'status': 'error', 'code': error.code}
