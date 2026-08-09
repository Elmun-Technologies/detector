from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class AnalysisStatus(StrEnum):
    UPLOADED = "uploaded"
    QUEUED = "queued"
    PROCESSING = "processing"
    TRANSCRIBING = "transcribing"
    VISUAL_ANALYSIS = "visual_analysis"
    SCORING = "scoring"
    REPORT_GENERATION = "report_generation"
    COMPLETED = "completed"
    FAILED = "failed"


class AccountProfile(BaseModel):
    account_type: Literal[
        "expert", "personal_brand", "service", "product", "marketplace",
        "education", "entertainment", "media", "local_business", "b2b",
    ] = "expert"
    niche: str | None = Field(default=None, max_length=120)
    language: Literal["uz", "ru", "en"] = "uz"
    average_views: int | None = Field(default=None, ge=0)
    best_views: int | None = Field(default=None, ge=0)
    followers: int | None = Field(default=None, ge=0)


class VideoContext(BaseModel):
    title: str | None = Field(default=None, max_length=160)
    topic: str | None = Field(default=None, max_length=500)
    objective: Literal["reach", "save", "share", "lead", "sales", "followers"] = "reach"
    audience: str | None = Field(default=None, max_length=500)
    transcript: str | None = Field(default=None, max_length=10000)
    duration_seconds: float | None = Field(default=None, ge=0, le=180)
    width: int | None = Field(default=None, ge=0)
    height: int | None = Field(default=None, ge=0)
    has_subtitles: bool | None = None
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


class Evidence(BaseModel):
    kind: Literal["verified_fact", "account_history", "external_source", "ai_inference", "insufficient_data"]
    label: str
    detail: str


class AnalysisReport(BaseModel):
    scores: ScoreBreakdown
    short_summary: str
    required_changes: list[str]
    improved_hooks: list[str]
    improved_cta: str
    editor_brief: list[str]
    segments: list[Segment]
    evidence: list[Evidence]
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
