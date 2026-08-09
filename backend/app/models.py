"""Production relational model. All media object keys are private, never public URLs."""
from __future__ import annotations
from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .database import Base

def now(): return datetime.now(timezone.utc)
def uid(): return str(uuid4())
class IdTime:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
class User(IdTime, Base):
    __tablename__='users'; telegram_id: Mapped[str|None]=mapped_column(String(32), unique=True); phone: Mapped[str|None]=mapped_column(String(32)); locale: Mapped[str]=mapped_column(String(12),default='uz'); deleted_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True)); workspaces=relationship('Workspace',back_populates='owner')
class Workspace(IdTime, Base):
    __tablename__='workspaces'; owner_id: Mapped[str]=mapped_column(ForeignKey('users.id')); name: Mapped[str]=mapped_column(String(160)); plan: Mapped[str]=mapped_column(String(20),default='free'); industry: Mapped[str|None]=mapped_column(String(120)); audience: Mapped[str|None]=mapped_column(Text); objective: Mapped[str|None]=mapped_column(String(80)); region: Mapped[str|None]=mapped_column(String(80)); owner=relationship('User',back_populates='workspaces')
class InstagramAccount(IdTime, Base):
    __tablename__='instagram_accounts'; workspace_id: Mapped[str]=mapped_column(ForeignKey('workspaces.id')); username: Mapped[str]=mapped_column(String(100)); account_type: Mapped[str]=mapped_column(String(32)); offer: Mapped[str|None]=mapped_column(Text); encrypted_token: Mapped[str|None]=mapped_column(Text); token_key_version: Mapped[str|None]=mapped_column(String(20)); active: Mapped[bool]=mapped_column(Boolean,default=True); __table_args__=(UniqueConstraint('workspace_id','username'),)
class Video(IdTime, Base):
    __tablename__='videos'; workspace_id: Mapped[str]=mapped_column(ForeignKey('workspaces.id')); account_id: Mapped[str|None]=mapped_column(ForeignKey('instagram_accounts.id')); storage_key: Mapped[str]=mapped_column(String(512)); original_name: Mapped[str]=mapped_column(String(255)); content_type: Mapped[str]=mapped_column(String(100)); size_bytes: Mapped[int]=mapped_column(Integer); duration_seconds: Mapped[float|None]=mapped_column(Float); width: Mapped[int|None]=mapped_column(Integer); height: Mapped[int|None]=mapped_column(Integer); status: Mapped[str]=mapped_column(String(32),default='uploaded')
class VideoAnalysis(IdTime, Base):
    __tablename__='video_analyses'; video_id: Mapped[str]=mapped_column(ForeignKey('videos.id'),unique=True); status: Mapped[str]=mapped_column(String(32),default='queued'); report: Mapped[dict|None]=mapped_column(JSON); media_metadata: Mapped[dict|None]=mapped_column('metadata', JSON); error: Mapped[str|None]=mapped_column(Text)
class VideoSegment(IdTime, Base):
    __tablename__='video_segments'; analysis_id: Mapped[str]=mapped_column(ForeignKey('video_analyses.id')); start_seconds: Mapped[float]=mapped_column(Float); end_seconds: Mapped[float]=mapped_column(Float); kind: Mapped[str]=mapped_column(String(40)); score: Mapped[float|None]=mapped_column(Float); details: Mapped[dict|None]=mapped_column(JSON)
class ContentPlan(IdTime, Base):
    __tablename__='content_plans'; workspace_id: Mapped[str]=mapped_column(ForeignKey('workspaces.id')); month: Mapped[str]=mapped_column(String(7)); title: Mapped[str]=mapped_column(String(160)); status: Mapped[str]=mapped_column(String(32),default='draft')
class ContentItem(IdTime, Base):
    __tablename__='content_items'; plan_id: Mapped[str]=mapped_column(ForeignKey('content_plans.id')); scheduled_for: Mapped[datetime|None]=mapped_column(DateTime(timezone=True)); topic: Mapped[str]=mapped_column(String(255)); hook: Mapped[str|None]=mapped_column(Text); script: Mapped[str|None]=mapped_column(Text); status: Mapped[str]=mapped_column(String(32),default='idea')
class Competitor(IdTime, Base):
    __tablename__='competitors'; workspace_id: Mapped[str]=mapped_column(ForeignKey('workspaces.id')); username: Mapped[str]=mapped_column(String(100)); notes: Mapped[str|None]=mapped_column(Text); last_analysis: Mapped[dict|None]=mapped_column(JSON); __table_args__=(UniqueConstraint('workspace_id','username'),)
class InstagramMetric(IdTime, Base):
    __tablename__='instagram_metrics'; video_id: Mapped[str]=mapped_column(ForeignKey('videos.id')); captured_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now); views: Mapped[int]=mapped_column(Integer,default=0); reach: Mapped[int]=mapped_column(Integer,default=0); likes: Mapped[int]=mapped_column(Integer,default=0); comments: Mapped[int]=mapped_column(Integer,default=0); shares: Mapped[int]=mapped_column(Integer,default=0); saves: Mapped[int]=mapped_column(Integer,default=0)
class Prediction(IdTime, Base):
    __tablename__='predictions'; video_id: Mapped[str]=mapped_column(ForeignKey('videos.id')); predicted_views: Mapped[int|None]=mapped_column(Integer); predicted_score: Mapped[float|None]=mapped_column(Float); actual_views: Mapped[int|None]=mapped_column(Integer); accuracy: Mapped[float|None]=mapped_column(Float)
class AuditLog(IdTime, Base):
    __tablename__='audit_logs'; workspace_id: Mapped[str|None]=mapped_column(ForeignKey('workspaces.id')); user_id: Mapped[str|None]=mapped_column(ForeignKey('users.id')); action: Mapped[str]=mapped_column(String(100)); target_type: Mapped[str|None]=mapped_column(String(60)); target_id: Mapped[str|None]=mapped_column(String(36)); ip_hash: Mapped[str|None]=mapped_column(String(64)); details: Mapped[dict|None]=mapped_column(JSON)
class AnalysisJob(IdTime, Base):
    __tablename__='analysis_jobs'; analysis_id: Mapped[str]=mapped_column(ForeignKey('video_analyses.id')); task_id: Mapped[str|None]=mapped_column(String(100)); status: Mapped[str]=mapped_column(String(32),default='queued'); attempts: Mapped[int]=mapped_column(Integer,default=0); locked_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
