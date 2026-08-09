from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

ALLOWED_CONTENT_TYPES = {
    "video/mp4",
    "video/quicktime",
    "video/x-msvideo",
    "application/octet-stream",  # Telegram may omit a precise content type.
}
ALLOWED_SUFFIXES = {".mp4", ".mov", ".avi"}


class VideoValidationError(ValueError):
    pass


@dataclass(frozen=True)
class VideoMetadata:
    duration_seconds: float | None = None
    width: int | None = None
    height: int | None = None
    has_audio: bool | None = None


def validate_upload(filename: str, content_type: str | None, size_bytes: int, max_upload_bytes: int) -> None:
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise VideoValidationError("Faqat MP4, MOV yoki AVI video qabul qilinadi.")
    if content_type and content_type not in ALLOWED_CONTENT_TYPES:
        raise VideoValidationError("Faylning Content-Type qiymati video formatiga mos emas.")
    if size_bytes <= 0:
        raise VideoValidationError("Bo‘sh faylni tahlil qilib bo‘lmaydi.")
    if size_bytes > max_upload_bytes:
        raise VideoValidationError(f"Fayl hajmi {max_upload_bytes // (1024 * 1024)} MB limitdan oshgan.")


def probe_video(path: Path) -> VideoMetadata:
    """Read metadata with ffprobe without executing a shell command.

    If ffprobe is not installed, the upload remains valid but video-specific
    checks are deferred to a processing worker. This keeps API behavior clear
    in a light development environment.
    """
    command = [
        "ffprobe", "-v", "error", "-show_entries",
        "format=duration:stream=codec_type,width,height", "-of", "json", str(path),
    ]
    try:
        output = subprocess.run(command, capture_output=True, check=True, text=True, timeout=20)
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return VideoMetadata()

    try:
        payload = json.loads(output.stdout)
        streams = payload.get("streams", [])
        video_stream = next((stream for stream in streams if stream.get("codec_type") == "video"), {})
        has_audio = any(stream.get("codec_type") == "audio" for stream in streams)
        duration = payload.get("format", {}).get("duration")
        return VideoMetadata(
            duration_seconds=round(float(duration), 2) if duration else None,
            width=video_stream.get("width"),
            height=video_stream.get("height"),
            has_audio=has_audio,
        )
    except (TypeError, ValueError, KeyError, json.JSONDecodeError):
        return VideoMetadata()
