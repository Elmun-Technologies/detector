"""Persisted workspace API (uploads, plans, competitors, metrics, reports).

Every workspace-scoped route resolves ownership through the RBAC layer before
touching data; nothing trusts a client supplied workspace id.
"""
from __future__ import annotations

import tempfile
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from . import analysis_service
from .auth import identity, require_workspace
from .config import settings
from .database import get_db
from .evidence import assert_clean
from .limits import assert_video_limit, entitlement
from .logging_setup import get_logger
from .models import (
    AuditLog,
    Competitor,
    ContentItem,
    ContentPlan,
    InstagramAccount,
    InstagramMetric,
    Prediction,
    User,
    Video,
    VideoAnalysis,
    Workspace,
    WorkspaceMember,
)
from .pdf_report import render_report_pdf
from .rbac import authorize_resource
from .schemas import VideoContext
from .security import hash_ip, rate_limit
from .storage import StorageError, get_storage, safe_filename, sha256_file, source_key
from .video import VideoValidationError, probe_upload, validate_upload

logger = get_logger('app.production_routes')
router = APIRouter(prefix='/v1', dependencies=[Depends(rate_limit)])


def audit(db: Session, request: Request, workspace: str | None, action: str, target: str | None = None, target_id: str | None = None) -> None:
    db.add(
        AuditLog(
            workspace_id=workspace,
            action=action,
            target_type=target,
            target_id=target_id,
            ip_hash=hash_ip(request.client.host if request.client else None),
        )
    )


class OnboardingIn(BaseModel):
    telegram_id: str | None = None
    phone: str | None = None
    name: str
    industry: str | None = None
    instagram_username: str
    account_type: str = 'creator'
    offer: str | None = None
    audience: str | None = None
    objective: str | None = None
    language: str = 'uz'
    region: str | None = None
    monthly_video_count: int = 0
    average_views: int | None = None
    max_views: int | None = None
    competitors: list[str] = []


class PlanIn(BaseModel):
    month: str = Field(pattern=r'^\d{4}-\d{2}$')
    title: str


class ItemIn(BaseModel):
    topic: str
    hook: str | None = None
    script: str | None = None
    scheduled_for: datetime | None = None


class CompetitorIn(BaseModel):
    username: str
    notes: str | None = None


class MetricsIn(BaseModel):
    views: int = 0
    reach: int = 0
    likes: int = 0
    comments: int = 0
    shares: int = 0
    saves: int = 0


class PlanUpdate(BaseModel):
    plan: str


@router.post('/onboarding', status_code=201)
def onboarding(payload: OnboardingIn, request: Request, db: Session = Depends(get_db)):
    user = db.query(User).filter_by(telegram_id=payload.telegram_id).first() if payload.telegram_id else None
    if not user:
        user = User(telegram_id=payload.telegram_id, phone=payload.phone, locale=payload.language)
        db.add(user)
        db.flush()
    workspace = Workspace(
        owner_id=user.id,
        name=payload.name,
        industry=payload.industry,
        audience=payload.audience,
        objective=payload.objective,
        region=payload.region,
    )
    db.add(workspace)
    db.flush()
    db.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role='owner'))
    db.add(
        InstagramAccount(
            workspace_id=workspace.id,
            username=payload.instagram_username.lstrip('@').lower(),
            account_type=payload.account_type,
            offer=payload.offer,
        )
    )
    for name in payload.competitors:
        db.add(Competitor(workspace_id=workspace.id, username=name.lstrip('@').lower()))
    audit(db, request, workspace.id, 'onboarding.completed', 'workspace', workspace.id)
    db.commit()
    return {'user_id': user.id, 'workspace_id': workspace.id, 'plan': workspace.plan}


@router.get('/workspaces/{workspace_id}')
def workspace(workspace_id: str, db: Session = Depends(get_db)):
    row = db.get(Workspace, workspace_id)
    if not row:
        raise HTTPException(404, 'Workspace not found')
    return {
        'id': row.id,
        'name': row.name,
        'plan': row.plan,
        'industry': row.industry,
        'usage_limit': entitlement(row.plan).videos_per_month,
    }


@router.patch('/workspaces/{workspace_id}/plan')
def update_plan(workspace_id: str, payload: PlanUpdate, request: Request, db: Session = Depends(get_db)):
    row = db.get(Workspace, workspace_id)
    if not row or payload.plan.lower() not in ('free', 'creator', 'pro', 'agency'):
        raise HTTPException(422, 'Invalid workspace or plan')
    row.plan = payload.plan.lower()
    audit(db, request, row.id, 'plan.updated', 'workspace', row.id)
    db.commit()
    return {'plan': row.plan, 'limits': entitlement(row.plan).__dict__}


@router.post('/workspaces/{workspace_id}/videos/upload', status_code=202)
async def persisted_upload(
    workspace_id: str,
    request: Request,
    file: UploadFile = File(...),
    context: str = Form('{}'),
    db: Session = Depends(get_db),
    user: str = Depends(identity),
    idempotency_key: str | None = Header(default=None, alias='Idempotency-Key'),
):
    """Direct multipart upload → private storage → queued analysis."""
    require_workspace(db, workspace_id, user, 'editor')
    workspace_row = db.get(Workspace, workspace_id)
    if not workspace_row:
        raise HTTPException(404, 'Workspace not found')
    try:
        assert_video_limit(db, workspace_id, workspace_row.plan)
    except PermissionError as error:
        raise HTTPException(429, str(error)) from error
    try:
        parsed = VideoContext.model_validate_json(context or '{}')
    except Exception as error:
        raise HTTPException(422, 'Invalid context JSON') from error

    name = safe_filename(file.filename or 'video.mp4')
    with tempfile.NamedTemporaryFile(delete=False, suffix=Path(name).suffix) as temporary:
        total = 0
        while chunk := await file.read(1024 * 1024):
            total += len(chunk)
            if total > settings.max_upload_bytes:
                temporary.close()
                Path(temporary.name).unlink(missing_ok=True)
                raise HTTPException(413, 'File too large')
            temporary.write(chunk)
        local = Path(temporary.name)
    await file.close()

    try:
        validate_upload(name, file.content_type, total)
        metadata = probe_upload(local)
        checksum = sha256_file(local)
    except VideoValidationError as error:
        local.unlink(missing_ok=True)
        raise HTTPException(422, str(error)) from error

    key = analysis_service.build_idempotency_key(workspace_id, checksum, idempotency_key)
    existing = analysis_service.find_job_by_key(db, key)
    if existing is not None:
        local.unlink(missing_ok=True)
        analysis = db.get(VideoAnalysis, existing.analysis_id)
        return {
            'video_id': analysis.video_id if analysis else None,
            'analysis_id': existing.analysis_id,
            'status': existing.status,
            'idempotent': True,
        }

    video = Video(
        workspace_id=workspace_id,
        storage_key='pending',
        original_name=name,
        content_type=file.content_type or 'application/octet-stream',
        size_bytes=total,
        duration_seconds=metadata.duration_seconds,
        width=metadata.width,
        height=metadata.height,
        status='queued',
        storage_backend=settings.storage_backend,
        checksum_sha256=checksum,
        video_codec=metadata.codec,
        aspect_ratio=metadata.aspect_ratio,
        has_audio=metadata.has_audio,
    )
    db.add(video)
    db.flush()
    try:
        stored = get_storage().put_file(local, source_key(workspace_id, video.id, name), video.content_type)
    except StorageError as error:
        local.unlink(missing_ok=True)
        db.rollback()
        status_code = 503 if error.retryable else 500
        raise HTTPException(status_code, f'Storage error: {error.code}') from error
    video.storage_key = stored.key

    analysis, job = analysis_service.create_analysis(db, video, parsed, key)
    audit(db, request, workspace_id, 'video.uploaded', 'video', video.id)
    db.commit()
    try:
        analysis_service.dispatch(db, job)
    except analysis_service.DispatchError as error:
        raise HTTPException(
            503,
            {
                'code': 'broker_unavailable',
                'message': 'Video saqlandi, lekin navbat vaqtincha ishlamayapti. Tahlil avtomatik qayta navbatga olinadi.',
                'video_id': video.id,
                'analysis_id': analysis.id,
            },
        ) from error
    return {'video_id': video.id, 'analysis_id': analysis.id, 'status': 'queued', 'idempotent': False}


@router.get('/analyses/persisted/{analysis_id}')
def persisted_analysis(analysis_id: str, db: Session = Depends(get_db), user: str = Depends(identity)):
    authorize_resource(db, 'analysis', analysis_id, user, 'viewer')
    row = db.get(VideoAnalysis, analysis_id)
    if not row:
        raise HTTPException(404, 'Analysis not found')
    payload = {
        'id': row.id,
        'status': row.status,
        'report': row.report,
        'metadata': row.media_metadata,
        'provider_mode': row.provider_mode,
        'language': row.language,
        'error_code': row.error_code,
        'error': row.error,
    }
    assert_clean(payload)
    return payload


@router.post('/workspaces/{workspace_id}/content-plans')
def create_plan(workspace_id: str, payload: PlanIn, request: Request, db: Session = Depends(get_db), user: str = Depends(identity)):
    require_workspace(db, workspace_id, user, 'editor')
    plan = ContentPlan(workspace_id=workspace_id, month=payload.month, title=payload.title)
    db.add(plan)
    audit(db, request, workspace_id, 'content_plan.created', 'content_plan')
    db.commit()
    db.refresh(plan)
    return {'id': plan.id, 'month': plan.month, 'title': plan.title, 'status': plan.status}


@router.get('/workspaces/{workspace_id}/content-plans')
def plans(workspace_id: str, db: Session = Depends(get_db), user: str = Depends(identity)):
    require_workspace(db, workspace_id, user, 'viewer')
    return [
        {'id': row.id, 'month': row.month, 'title': row.title, 'status': row.status}
        for row in db.query(ContentPlan).filter_by(workspace_id=workspace_id).all()
    ]


@router.post('/content-plans/{plan_id}/items')
def add_item(plan_id: str, payload: ItemIn, db: Session = Depends(get_db), user: str = Depends(identity)):
    authorize_resource(db, 'plan', plan_id, user, 'editor')
    if not db.get(ContentPlan, plan_id):
        raise HTTPException(404, 'Content plan not found')
    row = ContentItem(plan_id=plan_id, **payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return {'id': row.id, 'topic': row.topic, 'status': row.status}


@router.post('/workspaces/{workspace_id}/competitors')
def competitor(workspace_id: str, payload: CompetitorIn, request: Request, db: Session = Depends(get_db), user: str = Depends(identity)):
    require_workspace(db, workspace_id, user, 'editor')
    row = Competitor(workspace_id=workspace_id, username=payload.username.lstrip('@').lower(), notes=payload.notes)
    db.add(row)
    audit(db, request, workspace_id, 'competitor.created', 'competitor')
    db.commit()
    db.refresh(row)
    return {'id': row.id, 'username': row.username, 'notes': row.notes}


@router.get('/workspaces/{workspace_id}/competitors')
def competitors(workspace_id: str, db: Session = Depends(get_db), user: str = Depends(identity)):
    require_workspace(db, workspace_id, user, 'viewer')
    return [
        {'id': row.id, 'username': row.username, 'notes': row.notes, 'analysis': row.last_analysis}
        for row in db.query(Competitor).filter_by(workspace_id=workspace_id).all()
    ]


@router.post('/videos/{video_id}/metrics')
def metrics(video_id: str, payload: MetricsIn, db: Session = Depends(get_db), user: str = Depends(identity)):
    authorize_resource(db, 'video', video_id, user, 'editor')
    if not db.get(Video, video_id):
        raise HTTPException(404, 'Video not found')
    row = InstagramMetric(video_id=video_id, **payload.model_dump())
    prediction = db.query(Prediction).filter_by(video_id=video_id).first()
    if prediction and prediction.predicted_views:
        prediction.actual_views = payload.views
        prediction.accuracy = round(
            max(0, 1 - abs(payload.views - prediction.predicted_views) / max(prediction.predicted_views, 1)) * 100, 2
        )
    db.add(row)
    db.commit()
    return {'id': row.id, 'views': row.views, 'prediction_accuracy': prediction.accuracy if prediction else None}


@router.get('/videos/{video_id}/reports/{format}')
def export_report(format: str, video_id: str, db: Session = Depends(get_db), user: str = Depends(identity)):
    """Report export. Ownership is enforced before any bytes are produced."""
    authorize_resource(db, 'video', video_id, user, 'viewer')
    video = db.get(Video, video_id)
    analysis = db.query(VideoAnalysis).filter_by(video_id=video_id).first()
    if not video or not analysis:
        raise HTTPException(404, 'Video not found')

    if format == 'json':
        payload = {
            'video_id': video.id,
            'filename': video.original_name,
            'status': analysis.status,
            'provider_mode': analysis.provider_mode,
            'language': analysis.language,
            'report': analysis.report,
            'generated_at': datetime.now(timezone.utc).isoformat(),
        }
        assert_clean(payload)
        return payload
    if format == 'pdf':
        pdf = render_report_pdf(video.original_name, analysis.status, analysis.report, workspace=video.workspace_id)
        return Response(
            pdf,
            media_type='application/pdf',
            headers={'Content-Disposition': f'attachment; filename="report-{video.id}.pdf"'},
        )
    raise HTTPException(404, 'Format must be json or pdf')


@router.get('/admin/summary')
def admin_summary(db: Session = Depends(get_db), x_admin_key: str | None = Header(default=None, alias='X-Admin-Key')):
    """Operational counters. Requires ADMIN_API_KEY when one is configured."""
    if settings.admin_api_key and x_admin_key != settings.admin_api_key:
        raise HTTPException(401, 'Admin API key required')
    return {
        'users': db.query(User).count(),
        'workspaces': db.query(Workspace).count(),
        'videos': db.query(Video).count(),
        'analyses': db.query(VideoAnalysis).count(),
        'failed_analyses': db.query(VideoAnalysis).filter_by(status='failed').count(),
    }


@router.delete('/users/{user_id}')
def delete_user_data(user_id: str, request: Request, db: Session = Depends(get_db), user: str = Depends(identity)):
    """GDPR-style erasure: anonymise the user and purge their stored media."""
    if user_id != user:
        raise HTTPException(403, 'User ownership required')
    row = db.get(User, user_id)
    if not row:
        raise HTTPException(404, 'User not found')

    from .pipeline import purge_video_objects

    purged = 0
    workspaces = [workspace.id for workspace in db.query(Workspace).filter_by(owner_id=user_id).all()]
    if workspaces:
        for video in db.query(Video).filter(Video.workspace_id.in_(workspaces)).all():
            try:
                purged += purge_video_objects(db, video)
            except StorageError as error:  # pragma: no cover - storage best effort
                logger.warning('object purge failed', extra={'error_code': error.code})

    row.phone = None
    row.telegram_id = None
    row.deleted_at = datetime.now(timezone.utc)
    audit(db, request, None, 'user.data_deleted', 'user', user_id)
    db.commit()
    return {'status': 'deleted', 'objects_purged': purged}
