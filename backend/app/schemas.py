from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class AnalysisStatus(StrEnum):
    UPLOADED = "uploaded"
    QUEUED = "queued"
    PROCESSING = "processing"
    DOWNLOADING = "downloading"
    MEDIA_EXTRACTION = "media_extraction"
    TRANSCRIBING = "transcribing"
    VISUAL_ANALYSIS = "visual_analysis"
    SCORING = "scoring"
    REPORT_GENERATION = "report_generation"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AccountProfile(BaseModel):
    account_type: Literal[
        "expert", "personal_brand", "service", "product", "marketplace",
        "education", "entertainment", "media", "local_business", "b2b", "creator",
    ] = "expert"
    niche: str | None = Field(default=None, max_length=120)
    language: Literal["uz", "ru", "en", "mixed"] = "uz"
    average_views: int | None = Field(default=None, ge=0)
    best_views: int | None = Field(default=None, ge=0)
    followers: int | None = Field(default=None, ge=0)
    history_updated_on: date | None = None


class VideoContext(BaseModel):
    title: str | None = Field(default=None, max_length=160)
    topic: str | None = Field(default=None, max_length=500)
    objective: Literal["reach", "save", "share", "lead", "sales", "followers"] = "reach"
    audience: str | None = Field(default=None, max_length=500)
    transcript: str | None = Field(default=None, max_length=10000)
    duration_seconds: float | None = Field(default=None, ge=0, le=600)
    width: int | None = Field(default=None, ge=0)
    height: int | None = Field(default=None, ge=0)
    has_subtitles: bool | None = None
    language: Literal["uz", "ru", "en", "mixed"] | None = None
    account: AccountProfile = Field(default_factory=AccountProfile)


class Segment(BaseModel):
    start_time: float
    end_time: float
    title: str
    state: Literal["strong", "good", "risk"]
    retention_probability: int = Field(ge=0, le=100)
    issue: str
    recommendation: str


class ScoreBreakdown(BaseModel):
    viral_score: int = Field(ge=0, le=100)
    hook_score: int = Field(ge=0, le=100)
    retention_score: int = Field(ge=0, le=100)
    visual_score: int = Field(ge=0, le=100)
    audio_score: int = Field(ge=0, le=100)
    share_score: int = Field(ge=0, le=100)
    save_score: int = Field(ge=0, le=100)
    rewatch_score: int = Field(ge=0, le=100)
    clarity_score: int = Field(ge=0, le=100)
    audience_fit_score: int = Field(ge=0, le=100)
    cta_score: int = Field(ge=0, le=100)
    confidence: int = Field(ge=0, le=100)


EvidenceKindLiteral = Literal[
    "verified_fact", "account_history", "external_source", "ai_inference", "insufficient_data"
]


class Citation(BaseModel):
    """Source attached to a factual claim."""

    url: str = Field(max_length=1000)
    title: str = Field(max_length=300)
    publisher: str | None = Field(default=None, max_length=200)
    published_on: date | None = None
    accessed_on: date
    stale: bool = False


class Evidence(BaseModel):
    """Provenance of one report signal.

    ``kind`` is the fact policy: measured facts, the account's own history,
    an external cited source, model inference, or an explicit gap.
    """

    kind: EvidenceKindLiteral
    label: str
    detail: str
    signal: str | None = None
    confidence: int | None = Field(default=None, ge=0, le=100)
    source_date: date | None = None
    stale: bool = False
    citations: list[Citation] = Field(default_factory=list)


class TimelineSecond(BaseModel):
    second: int = Field(ge=0)
    retention_probability: int = Field(ge=0, le=100)
    scene_change: bool = False
    silence: bool = False
    speech: bool = False
    label: str
    note: str | None = None
    evidence_kind: EvidenceKindLiteral = "ai_inference"


class PredictionRange(BaseModel):
    basis: Literal["account_history", "insufficient_data"]
    low_views: int | None = None
    expected_views: int | None = None
    high_views: int | None = None
    confidence: int = Field(ge=0, le=100)
    note: str


class ThumbnailCandidate(BaseModel):
    timestamp_seconds: float
    storage_key: str | None = None
    reason: str


class MediaSummary(BaseModel):
    duration_seconds: float | None = None
    width: int | None = None
    height: int | None = None
    aspect_ratio: str | None = None
    is_vertical: bool | None = None
    video_codec: str | None = None
    audio_codec: str | None = None
    has_audio: bool = False
    fps: float | None = None
    scene_change_count: int = 0
    scene_change_rate: float | None = None
    silence_seconds: float = 0.0
    speech_ratio: float | None = None
    frame_count: int = 0
    keyframe_count: int = 0
    thumbnails: list[ThumbnailCandidate] = Field(default_factory=list)
    analysed: bool = False


class ProviderUsageSummary(BaseModel):
    calls: list[dict] = Field(default_factory=list)
    total_cost_usd: float = 0.0
    total_tokens: int = 0
    modes: list[str] = Field(default_factory=list)


class AnalysisReport(BaseModel):
    scores: ScoreBreakdown
    short_summary: str
    required_changes: list[str]
    improved_hooks: list[str]
    improved_cta: str
    editor_brief: list[str]
    segments: list[Segment]
    evidence: list[Evidence]
    improved_script: list[str] = Field(default_factory=list)
    timeline: list[TimelineSecond] = Field(default_factory=list)
    prediction: PredictionRange | None = None
    media: MediaSummary | None = None
    usage: ProviderUsageSummary | None = None
    language: str = "uz"
    provider_mode: Literal["production", "demo", "unconfigured"] = "demo"
    generated_at: datetime | None = None
    disclaimer: str = "Bu prognoz kafolat emas. U video signallari, berilgan kontekst va mavjud akkaunt benchmarkiga asoslangan ehtimoliy bahodir."


class AnalysisJob(BaseModel):
    id: str
    status: AnalysisStatus
    created_at: datetime
    updated_at: datetime
    source_filename: str | None = None
    context: VideoContext
    report: AnalysisReport | None = None
    error: str | None = None


class CreateAnalysisRequest(BaseModel):
    """Use this endpoint for manual data, URL-derived metadata or a Mini App."""

    context: VideoContext
    source_filename: str | None = Field(default=None, max_length=255)


class IdeaCheckRequest(BaseModel):
    idea: str = Field(min_length=8, max_length=1000)
    objective: Literal["reach", "save", "share", "lead", "sales", "followers"] = "reach"
    format: str = Field(default="expert_reels", max_length=80)
    account: AccountProfile = Field(default_factory=AccountProfile)


class IdeaCheckResponse(BaseModel):
    potential_score: int = Field(ge=0, le=100)
    audience_fit: int = Field(ge=0, le=100)
    save_potential: int = Field(ge=0, le=100)
    novelty: int = Field(ge=0, le=100)
    competition: Literal["low", "medium", "high"]
    optimal_duration_seconds: tuple[int, int]
    improved_angle: str
    hooks: list[str]
    fact_check_needed: list[str]
    disclaimer: str


class JobProgress(BaseModel):
    analysis_id: str
    job_id: str
    status: str
    stage: str | None = None
    progress: int = Field(ge=0, le=100)
    attempts: int = 0
    max_attempts: int = 0
    error_code: str | None = None
    error: str | None = None
    cancel_requested: bool = False
    updated_at: datetime | None = None
