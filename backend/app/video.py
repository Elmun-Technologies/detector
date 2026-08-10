"""Upload validation helpers.

Thin, dependency-light layer over :mod:`app.media`. The API uses it during
request handling (fast checks); the worker uses :mod:`app.media` directly for
the full extraction pipeline.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import media
from .config import settings

ALLOWED_CONTENT_TYPES = {'video/mp4', 'video/quicktime', 'video/x-msvideo', 'application/octet-stream'}
ALLOWED_SUFFIXES = {'.mp4', '.mov', '.avi'}


class VideoValidationError(ValueError):
    """Raised when an upload is rejected before it reaches storage."""


@dataclass(frozen=True)
class VideoMetadata:
    duration_seconds: float | None = None
    width: int | None = None
    height: int | None = None
    has_audio: bool | None = None
    vertical: bool | None = None
    silence_seconds: float | None = None
    codec: str | None = None
    aspect_ratio: str | None = None


def validate_upload(filename: str, content_type: str | None, size_bytes: int, max_upload_bytes: int | None = None) -> None:
    limit = max_upload_bytes or settings.max_upload_bytes
    if Path(filename).suffix.lower() not in ALLOWED_SUFFIXES:
        raise VideoValidationError('Faqat MP4, MOV yoki AVI video qabul qilinadi.')
    if content_type and content_type not in ALLOWED_CONTENT_TYPES:
        raise VideoValidationError('Faylning Content-Type qiymati video formatiga mos emas.')
    if size_bytes <= 0:
        raise VideoValidationError('Bo‘sh faylni tahlil qilib bo‘lmaydi.')
    if size_bytes > limit:
        raise VideoValidationError(f'Fayl hajmi {limit // (1024 * 1024)} MB limitdan oshgan.')


def probe_video(path: Path) -> VideoMetadata:
    """Best-effort probe used by request handlers.

    Returns empty metadata when FFprobe is unavailable so an upload is not
    rejected for a missing local tool; the worker performs the authoritative
    (and strict) probe.
    """
    try:
        result = media.probe(path)
    except media.MediaError:
        return VideoMetadata()
    return VideoMetadata(
        duration_seconds=result.duration_seconds,
        width=result.width,
        height=result.height,
        has_audio=result.has_audio,
        vertical=result.is_vertical,
        codec=result.video_codec,
        aspect_ratio=result.aspect_ratio,
    )


def probe_upload(path: Path) -> VideoMetadata:
    """Request-time probe.

    When FFprobe is installed next to the API an unreadable container is
    rejected immediately (422) instead of wasting a queue slot. When the tool
    is missing the check is skipped — the worker still performs the strict,
    authoritative probe before any provider is called.
    """
    try:
        result = media.probe(path)
        media.assert_playable(result)
    except media.MediaToolUnavailableError:
        return VideoMetadata()
    except media.MediaError as error:
        raise VideoValidationError('Video fayli buzilgan yoki formati qo‘llab-quvvatlanmaydi.') from error
    return VideoMetadata(
        duration_seconds=result.duration_seconds,
        width=result.width,
        height=result.height,
        has_audio=result.has_audio,
        vertical=result.is_vertical,
        codec=result.video_codec,
        aspect_ratio=result.aspect_ratio,
    )


def probe_video_strict(path: Path) -> media.MediaProbe:
    """Authoritative probe: raises on unreadable/corrupted media."""
    result = media.probe(path)
    media.assert_playable(result)
    return result


def detect_silence(path: Path) -> float | None:
    """Total silence duration in seconds, or ``None`` when FFmpeg is missing."""
    try:
        windows = media.detect_silence(path)
    except media.MediaError:
        return None
    return round(sum(window.duration_seconds for window in windows), 2)
