"""Production relational model.

All media is referenced by a private object-storage key; the database never
stores a public URL, a provider secret or a raw provider response body.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def now() -> datetime:
    return datetime.now(timezone.utc)


def uid() -> str:
    return str(uuid4())


class IdTime:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class User(IdTime, Base):
    __tablename__ = 'users'
    telegram_id: Mapped[str | None] = mapped_column(String(32), unique=True)
    phone: Mapped[str | None] = mapped_column(String(32))
    locale: Mapped[str] = mapped_column(String(12), default='uz')
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    workspaces = relationship('Workspace', back_populates='owner')


class Workspace(IdTime, Base):
    __tablename__ = 'workspaces'
    owner_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    name: Mapped[str] = mapped_column(String(160))
    plan: Mapped[str] = mapped_column(String(20), default='free')
    industry: Mapped[str | None] = mapped_column(String(120))
    audience: Mapped[str | None] = mapped_column(Text)
    objective: Mapped[str | None] = mapped_column(String(80))
    region: Mapped[str | None] = mapped_column(String(80))
    owner = relationship('User', back_populates='workspaces')


class WorkspaceMember(IdTime, Base):
    __tablename__ = 'workspace_members'
    workspace_id: Mapped[str] = mapped_column(ForeignKey('workspaces.id'))
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    role: Mapped[str] = mapped_column(String(16), default='viewer')
    __table_args__ = (UniqueConstraint('workspace_id', 'user_id'),)


class Role(IdTime, Base):
    __tablename__ = 'roles'
    name: Mapped[str] = mapped_column(String(32), unique=True)
    permissions: Mapped[dict] = mapped_column(JSON, default=dict)


class Subscription(IdTime, Base):
    __tablename__ = 'subscriptions'
    workspace_id: Mapped[str] = mapped_column(ForeignKey('workspaces.id'), unique=True)
    plan: Mapped[str] = mapped_column(String(20), default='free')
    status: Mapped[str] = mapped_column(String(20), default='active')
    provider: Mapped[str | None] = mapped_column(String(20))
    external_id: Mapped[str | None] = mapped_column(String(128))


class Payment(IdTime, Base):
    __tablename__ = 'payments'
    workspace_id: Mapped[str] = mapped_column(ForeignKey('workspaces.id'))
    provider: Mapped[str] = mapped_column(String(20))
    provider_payment_id: Mapped[str | None] = mapped_column(String(128), unique=True)
    amount: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(8), default='UZS')
    status: Mapped[str] = mapped_column(String(20), default='pending')
    raw_event: Mapped[dict | None] = mapped_column(JSON)


class InstagramAccount(IdTime, Base):
    __tablename__ = 'instagram_accounts'
    workspace_id: Mapped[str] = mapped_column(ForeignKey('workspaces.id'))
    username: Mapped[str] = mapped_column(String(100))
    account_type: Mapped[str] = mapped_column(String(32))
    offer: Mapped[str | None] = mapped_column(Text)
    encrypted_token: Mapped[str | None] = mapped_column(Text)
    token_key_version: Mapped[str | None] = mapped_column(String(20))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (UniqueConstraint('workspace_id', 'username'),)


class Video(IdTime, Base):
    __tablename__ = 'videos'
    workspace_id: Mapped[str] = mapped_column(ForeignKey('workspaces.id'))
    account_id: Mapped[str | None] = mapped_column(ForeignKey('instagram_accounts.id'))
    storage_key: Mapped[str] = mapped_column(String(512))
    original_name: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    duration_seconds: Mapped[float | None] = mapped_column(Float)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), default='uploaded')
    # Milestone 2: measured media facts and storage provenance.
    storage_backend: Mapped[str | None] = mapped_column(String(16))
    checksum_sha256: Mapped[str | None] = mapped_column(String(64))
    video_codec: Mapped[str | None] = mapped_column(String(32))
    audio_codec: Mapped[str | None] = mapped_column(String(32))
    aspect_ratio: Mapped[str | None] = mapped_column(String(16))
    fps: Mapped[float | None] = mapped_column(Float)
    has_audio: Mapped[bool | None] = mapped_column(Boolean)


class VideoAnalysis(IdTime, Base):
    __tablename__ = 'video_analyses'
    video_id: Mapped[str] = mapped_column(ForeignKey('videos.id'), unique=True)
    status: Mapped[str] = mapped_column(String(32), default='queued')
    report: Mapped[dict | None] = mapped_column(JSON)
    media_metadata: Mapped[dict | None] = mapped_column('metadata', JSON)
    error: Mapped[str | None] = mapped_column(Text)
    # Milestone 2: run provenance.
    language: Mapped[str | None] = mapped_column(String(12))
    provider_mode: Mapped[str | None] = mapped_column(String(16))
    cost_usd: Mapped[float | None] = mapped_column(Float)
    error_code: Mapped[str | None] = mapped_column(String(64))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class VideoSegment(IdTime, Base):
    __tablename__ = 'video_segments'
    analysis_id: Mapped[str] = mapped_column(ForeignKey('video_analyses.id'))
    start_seconds: Mapped[float] = mapped_column(Float)
    end_seconds: Mapped[float] = mapped_column(Float)
    kind: Mapped[str] = mapped_column(String(40))
    score: Mapped[float | None] = mapped_column(Float)
    details: Mapped[dict | None] = mapped_column(JSON)


class MediaArtifact(IdTime, Base):
    """Derived media file (audio track, frame, keyframe, thumbnail) in private storage."""

    __tablename__ = 'media_artifacts'
    video_id: Mapped[str] = mapped_column(ForeignKey('videos.id'))
    analysis_id: Mapped[str | None] = mapped_column(ForeignKey('video_analyses.id'))
    kind: Mapped[str] = mapped_column(String(32))
    storage_key: Mapped[str] = mapped_column(String(512))
    content_type: Mapped[str | None] = mapped_column(String(80))
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    timestamp_seconds: Mapped[float | None] = mapped_column(Float)
    artifact_metadata: Mapped[dict | None] = mapped_column('metadata', JSON)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (Index('ix_media_artifacts_video', 'video_id', 'kind'),)


class ProviderCall(IdTime, Base):
    """Cost/latency ledger for AI provider calls. Raw payloads are never stored."""

    __tablename__ = 'provider_calls'
    analysis_id: Mapped[str] = mapped_column(ForeignKey('video_analyses.id'))
    kind: Mapped[str] = mapped_column(String(24))
    provider: Mapped[str] = mapped_column(String(48))
    model: Mapped[str | None] = mapped_column(String(64))
    mode: Mapped[str] = mapped_column(String(16), default='production')
    status: Mapped[str] = mapped_column(String(16), default='ok')
    attempts: Mapped[int] = mapped_column(Integer, default=1)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    error_code: Mapped[str | None] = mapped_column(String(64))


class ContentPlan(IdTime, Base):
    __tablename__ = 'content_plans'
    workspace_id: Mapped[str] = mapped_column(ForeignKey('workspaces.id'))
    month: Mapped[str] = mapped_column(String(7))
    title: Mapped[str] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(32), default='draft')


class ContentItem(IdTime, Base):
    __tablename__ = 'content_items'
    plan_id: Mapped[str] = mapped_column(ForeignKey('content_plans.id'))
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    topic: Mapped[str] = mapped_column(String(255))
    hook: Mapped[str | None] = mapped_column(Text)
    script: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default='idea')


class Competitor(IdTime, Base):
    __tablename__ = 'competitors'
    workspace_id: Mapped[str] = mapped_column(ForeignKey('workspaces.id'))
    username: Mapped[str] = mapped_column(String(100))
    notes: Mapped[str | None] = mapped_column(Text)
    last_analysis: Mapped[dict | None] = mapped_column(JSON)
    __table_args__ = (UniqueConstraint('workspace_id', 'username'),)


class InstagramMetric(IdTime, Base):
    __tablename__ = 'instagram_metrics'
    video_id: Mapped[str] = mapped_column(ForeignKey('videos.id'))
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    views: Mapped[int] = mapped_column(Integer, default=0)
    reach: Mapped[int] = mapped_column(Integer, default=0)
    likes: Mapped[int] = mapped_column(Integer, default=0)
    comments: Mapped[int] = mapped_column(Integer, default=0)
    shares: Mapped[int] = mapped_column(Integer, default=0)
    saves: Mapped[int] = mapped_column(Integer, default=0)


class Prediction(IdTime, Base):
    __tablename__ = 'predictions'
    video_id: Mapped[str] = mapped_column(ForeignKey('videos.id'))
    predicted_views: Mapped[int | None] = mapped_column(Integer)
    predicted_score: Mapped[float | None] = mapped_column(Float)
    actual_views: Mapped[int | None] = mapped_column(Integer)
    accuracy: Mapped[float | None] = mapped_column(Float)


class AuditLog(IdTime, Base):
    __tablename__ = 'audit_logs'
    workspace_id: Mapped[str | None] = mapped_column(ForeignKey('workspaces.id'))
    user_id: Mapped[str | None] = mapped_column(ForeignKey('users.id'))
    action: Mapped[str] = mapped_column(String(100))
    target_type: Mapped[str | None] = mapped_column(String(60))
    target_id: Mapped[str | None] = mapped_column(String(36))
    ip_hash: Mapped[str | None] = mapped_column(String(64))
    details: Mapped[dict | None] = mapped_column(JSON)


class AnalysisJob(IdTime, Base):
    __tablename__ = 'analysis_jobs'
    analysis_id: Mapped[str] = mapped_column(ForeignKey('video_analyses.id'))
    task_id: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(32), default='queued')
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Milestone 2: idempotency, progress, retry and recovery bookkeeping.
    idempotency_key: Mapped[str | None] = mapped_column(String(128), unique=True)
    stage: Mapped[str | None] = mapped_column(String(32))
    progress: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    error_code: Mapped[str | None] = mapped_column(String(64))
    error: Mapped[str | None] = mapped_column(Text)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
