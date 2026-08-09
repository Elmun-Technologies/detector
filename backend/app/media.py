"""FFmpeg/FFprobe media pipeline.

Responsibilities:

* validate the container (codecs, duration, resolution, aspect ratio, audio
  track, corruption);
* extract the artifacts the AI stage needs: audio track, sampled frames,
  keyframes, scene-change map, silence map and thumbnail/cover candidates.

Every observation returned here is *measured*. When FFmpeg is unavailable the
functions raise :class:`MediaToolUnavailableError` instead of inventing values,
so the report layer can label the signal ``insufficient_data``.
"""
from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path

from .config import settings
from .logging_setup import get_logger

logger = get_logger('app.media')


# --------------------------------------------------------------------------- errors
class MediaError(RuntimeError):
    code = 'media_error'
    retryable = False


class MediaToolUnavailableError(MediaError):
    code = 'media_tool_unavailable'


class MediaTimeoutError(MediaError):
    code = 'media_timeout'
    retryable = True


class MediaProcessingError(MediaError):
    code = 'media_processing_failed'
    retryable = True


class MediaCorruptedError(MediaError):
    code = 'media_corrupted'


class MediaValidationError(MediaError):
    code = 'media_validation_failed'


# --------------------------------------------------------------------------- value objects
@dataclass(frozen=True)
class MediaProbe:
    container: str | None
    duration_seconds: float | None
    size_bytes: int
    bitrate_kbps: int | None
    video_codec: str | None
    width: int | None
    height: int | None
    fps: float | None
    aspect_ratio: str | None
    aspect_ratio_value: float | None
    is_vertical: bool | None
    has_audio: bool
    audio_codec: str | None
    audio_channels: int | None
    audio_sample_rate: int | None
    corrupt: bool = False
    corruption_reason: str | None = None
    warnings: tuple[str, ...] = ()

    def to_metadata(self) -> dict:
        return {
            'container': self.container,
            'duration_seconds': self.duration_seconds,
            'size_bytes': self.size_bytes,
            'bitrate_kbps': self.bitrate_kbps,
            'video_codec': self.video_codec,
            'width': self.width,
            'height': self.height,
            'fps': self.fps,
            'aspect_ratio': self.aspect_ratio,
            'aspect_ratio_value': self.aspect_ratio_value,
            'is_vertical': self.is_vertical,
            'has_audio': self.has_audio,
            'audio_codec': self.audio_codec,
            'audio_channels': self.audio_channels,
            'audio_sample_rate': self.audio_sample_rate,
            'corrupt': self.corrupt,
            'corruption_reason': self.corruption_reason,
            'warnings': list(self.warnings),
        }


@dataclass(frozen=True)
class FrameArtifact:
    path: Path
    timestamp_seconds: float
    kind: str
    size_bytes: int


@dataclass(frozen=True)
class AudioArtifact:
    path: Path
    duration_seconds: float | None
    sample_rate: int
    channels: int
    size_bytes: int


@dataclass(frozen=True)
class SilenceWindow:
    start_seconds: float
    end_seconds: float

    @property
    def duration_seconds(self) -> float:
        return round(max(0.0, self.end_seconds - self.start_seconds), 3)


@dataclass(frozen=True)
class SceneChange:
    timestamp_seconds: float
    score: float


@dataclass
class MediaBundle:
    probe: MediaProbe
    audio: AudioArtifact | None = None
    frames: list[FrameArtifact] = field(default_factory=list)
    keyframes: list[FrameArtifact] = field(default_factory=list)
    thumbnails: list[FrameArtifact] = field(default_factory=list)
    scene_changes: list[SceneChange] = field(default_factory=list)
    silences: list[SilenceWindow] = field(default_factory=list)
    tool_versions: dict[str, str] = field(default_factory=dict)

    @property
    def silence_seconds(self) -> float:
        return round(sum(window.duration_seconds for window in self.silences), 2)

    @property
    def speech_ratio(self) -> float | None:
        duration = self.probe.duration_seconds
        if not duration:
            return None
        return round(max(0.0, min(1.0, 1 - self.silence_seconds / duration)), 3)

    @property
    def scene_change_rate(self) -> float | None:
        duration = self.probe.duration_seconds
        if not duration:
            return None
        return round(len(self.scene_changes) / duration, 3)

    def to_metadata(self) -> dict:
        return {
            **self.probe.to_metadata(),
            'silence_seconds': self.silence_seconds,
            'silence_windows': [
                {'start': window.start_seconds, 'end': window.end_seconds, 'duration': window.duration_seconds}
                for window in self.silences
            ],
            'speech_ratio': self.speech_ratio,
            'scene_changes': [
                {'timestamp': scene.timestamp_seconds, 'score': scene.score} for scene in self.scene_changes
            ],
            'scene_change_rate': self.scene_change_rate,
            'frame_count': len(self.frames),
            'keyframe_count': len(self.keyframes),
            'thumbnail_count': len(self.thumbnails),
            'tool_versions': self.tool_versions,
        }


# --------------------------------------------------------------------------- process helpers
def resolve_binary(configured: str, name: str) -> str:
    path = shutil.which(configured) or (configured if Path(configured).exists() else None)
    if not path:
        raise MediaToolUnavailableError(f'{name} binary not found (configured as {configured!r})')
    return path


def ffmpeg_binary() -> str:
    return resolve_binary(settings.ffmpeg_binary, 'ffmpeg')


def ffprobe_binary() -> str:
    return resolve_binary(settings.ffprobe_binary, 'ffprobe')


def tools_available() -> bool:
    try:
        ffmpeg_binary()
        ffprobe_binary()
        return True
    except MediaToolUnavailableError:
        return False


def tool_versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    for label, resolver in (('ffmpeg', ffmpeg_binary), ('ffprobe', ffprobe_binary)):
        try:
            output = subprocess.run([resolver(), '-version'], capture_output=True, text=True, timeout=10)
            versions[label] = output.stdout.splitlines()[0][:120] if output.stdout else 'unknown'
        except (MediaToolUnavailableError, subprocess.SubprocessError):
            versions[label] = 'unavailable'
    return versions


def _run(command: list[str], timeout: int, *, allow_failure: bool = False) -> subprocess.CompletedProcess:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError as error:
        raise MediaToolUnavailableError(f'Media tool missing: {command[0]}') from error
    except subprocess.TimeoutExpired as error:
        raise MediaTimeoutError(f'Media command timed out after {timeout}s: {command[0]}') from error
    if result.returncode != 0 and not allow_failure:
        tail = (result.stderr or '').strip().splitlines()[-3:]
        raise MediaProcessingError(f'{Path(command[0]).name} failed: ' + ' | '.join(tail)[:500])
    return result


# --------------------------------------------------------------------------- probing
def ffprobe_json(path: Path) -> dict:
    result = _run(
        [
            ffprobe_binary(), '-v', 'error', '-show_error', '-show_format', '-show_streams',
            '-of', 'json', str(path),
        ],
        timeout=settings.ffprobe_timeout_seconds,
        allow_failure=True,
    )
    try:
        data = json.loads(result.stdout or '{}')
    except json.JSONDecodeError as error:
        raise MediaCorruptedError('FFprobe returned unparsable output; the container is not readable') from error
    if result.returncode != 0 or 'error' in data:
        detail = data.get('error', {}).get('string') or (result.stderr or '').strip().splitlines()[-1:]
        raise MediaCorruptedError(f'Unreadable media container: {detail}')
    return data


# Ratios an editor actually works with; anything within 1.5% snaps to the label.
STANDARD_RATIOS = {
    '9:16': 9 / 16,
    '4:5': 4 / 5,
    '3:4': 3 / 4,
    '1:1': 1.0,
    '4:3': 4 / 3,
    '16:9': 16 / 9,
    '2:1': 2.0,
}


def _aspect_ratio(width: int | None, height: int | None) -> tuple[str | None, float | None]:
    if not width or not height:
        return None, None
    value = round(width / height, 4)
    for label, target in STANDARD_RATIOS.items():
        if abs(value - target) / target <= 0.015:
            return label, value
    exact = Fraction(width, height)
    return f'{exact.numerator}:{exact.denominator}', value


def _fps(stream: dict) -> float | None:
    for key in ('avg_frame_rate', 'r_frame_rate'):
        value = stream.get(key)
        if value and value != '0/0':
            try:
                numerator, denominator = value.split('/')
                if float(denominator):
                    return round(float(numerator) / float(denominator), 3)
            except (ValueError, ZeroDivisionError):
                continue
    return None


def deep_integrity_check(path: Path) -> str | None:
    """Decode the whole file and report the first decoding error, if any."""
    result = _run(
        [ffmpeg_binary(), '-v', 'error', '-xerror', '-i', str(path), '-f', 'null', '-'],
        timeout=settings.ffmpeg_timeout_seconds,
        allow_failure=True,
    )
    if result.returncode != 0:
        line = (result.stderr or '').strip().splitlines()[-1:] or ['decoder reported an error']
        return line[0][:200]
    return None


def probe(path: Path, deep: bool = False) -> MediaProbe:
    """Return measured container metadata; raise when the file is unreadable."""
    if not path.exists():
        raise MediaValidationError(f'Media file does not exist: {path}')
    size_bytes = path.stat().st_size
    if size_bytes == 0:
        raise MediaCorruptedError('Media file is empty')

    data = ffprobe_json(path)
    streams = data.get('streams', [])
    fmt = data.get('format', {})
    video = next((stream for stream in streams if stream.get('codec_type') == 'video'), None)
    audio = next((stream for stream in streams if stream.get('codec_type') == 'audio'), None)

    warnings: list[str] = []
    duration = fmt.get('duration') or (video or {}).get('duration')
    duration_seconds = round(float(duration), 3) if duration not in (None, 'N/A') else None
    width = video.get('width') if video else None
    height = video.get('height') if video else None
    ratio_label, ratio_value = _aspect_ratio(width, height)
    bitrate = fmt.get('bit_rate')

    corruption_reason: str | None = None
    if video is None:
        corruption_reason = 'No video stream found in the container'
    elif not duration_seconds or duration_seconds <= 0:
        corruption_reason = 'Container reports no usable duration'
    elif not width or not height:
        corruption_reason = 'Video stream reports no frame size'

    if audio is None:
        warnings.append('no_audio_track')
    if ratio_value and ratio_value > 1:
        warnings.append('horizontal_aspect_ratio')
    if duration_seconds and duration_seconds > settings.max_duration_seconds:
        warnings.append('duration_over_limit')

    if deep and corruption_reason is None:
        decoding_error = deep_integrity_check(path)
        if decoding_error:
            corruption_reason = f'Decoder error: {decoding_error}'

    return MediaProbe(
        container=fmt.get('format_name'),
        duration_seconds=duration_seconds,
        size_bytes=size_bytes,
        bitrate_kbps=round(int(bitrate) / 1000) if bitrate and str(bitrate).isdigit() else None,
        video_codec=(video or {}).get('codec_name'),
        width=width,
        height=height,
        fps=_fps(video) if video else None,
        aspect_ratio=ratio_label,
        aspect_ratio_value=ratio_value,
        is_vertical=bool(width and height and height >= width),
        has_audio=audio is not None,
        audio_codec=(audio or {}).get('codec_name'),
        audio_channels=int(audio['channels']) if audio and str(audio.get('channels', '')).isdigit() else None,
        audio_sample_rate=int(audio['sample_rate']) if audio and str(audio.get('sample_rate', '')).isdigit() else None,
        corrupt=corruption_reason is not None,
        corruption_reason=corruption_reason,
        warnings=tuple(warnings),
    )


def assert_playable(media: MediaProbe) -> None:
    if media.corrupt:
        raise MediaCorruptedError(media.corruption_reason or 'Media file is corrupted')


# --------------------------------------------------------------------------- extraction
def extract_audio(path: Path, destination: Path, sample_rate: int | None = None) -> AudioArtifact:
    """Extract a mono PCM WAV track suitable for speech-to-text providers."""
    rate = sample_rate or settings.audio_sample_rate
    destination.parent.mkdir(parents=True, exist_ok=True)
    _run(
        [
            ffmpeg_binary(), '-y', '-v', 'error', '-i', str(path), '-vn',
            '-ac', '1', '-ar', str(rate), '-c:a', 'pcm_s16le', str(destination),
        ],
        timeout=settings.ffmpeg_timeout_seconds,
    )
    if not destination.exists() or destination.stat().st_size == 0:
        raise MediaProcessingError('Audio extraction produced an empty file')
    size = destination.stat().st_size
    # 16-bit mono PCM: bytes / (2 * sample rate) = seconds.
    duration = round(max(0.0, (size - 44) / (2 * rate)), 3)
    return AudioArtifact(path=destination, duration_seconds=duration, sample_rate=rate, channels=1, size_bytes=size)


def sample_frames(path: Path, out_dir: Path, interval_seconds: float | None = None, limit: int | None = None) -> list[FrameArtifact]:
    """Evenly sample frames across the video for vision/OCR providers."""
    interval = interval_seconds or settings.frame_sample_interval_seconds
    maximum = limit or settings.frame_sample_max
    out_dir.mkdir(parents=True, exist_ok=True)
    pattern = str(out_dir / 'frame-%04d.jpg')
    _run(
        [
            ffmpeg_binary(), '-y', '-v', 'error', '-i', str(path),
            '-vf', f'fps=1/{interval},scale=640:-2', '-frames:v', str(maximum), '-q:v', '4', pattern,
        ],
        timeout=settings.ffmpeg_timeout_seconds,
    )
    frames: list[FrameArtifact] = []
    for index, file in enumerate(sorted(out_dir.glob('frame-*.jpg'))):
        frames.append(
            FrameArtifact(
                path=file,
                timestamp_seconds=round(index * interval, 3),
                kind='frame',
                size_bytes=file.stat().st_size,
            )
        )
    return frames


def keyframe_timestamps(path: Path, limit: int | None = None) -> list[float]:
    maximum = limit or settings.keyframe_max
    result = _run(
        [
            ffprobe_binary(), '-v', 'error', '-select_streams', 'v:0', '-skip_frame', 'nokey',
            '-show_entries', 'frame=best_effort_timestamp_time', '-of', 'json', str(path),
        ],
        timeout=settings.ffprobe_timeout_seconds,
        allow_failure=True,
    )
    try:
        frames = json.loads(result.stdout or '{}').get('frames', [])
    except json.JSONDecodeError:
        return []
    stamps: list[float] = []
    for frame in frames:
        value = frame.get('best_effort_timestamp_time')
        if value in (None, 'N/A'):
            continue
        try:
            stamps.append(round(float(value), 3))
        except ValueError:
            continue
    if len(stamps) <= maximum:
        return stamps
    step = len(stamps) / maximum
    return [stamps[min(len(stamps) - 1, int(index * step))] for index in range(maximum)]


def extract_frame_at(path: Path, timestamp: float, destination: Path, width: int = 640) -> FrameArtifact | None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    result = _run(
        [
            ffmpeg_binary(), '-y', '-v', 'error', '-ss', f'{max(0.0, timestamp):.3f}', '-i', str(path),
            '-frames:v', '1', '-vf', f'scale={width}:-2', '-q:v', '4', str(destination),
        ],
        timeout=settings.ffmpeg_timeout_seconds,
        allow_failure=True,
    )
    if result.returncode != 0 or not destination.exists() or destination.stat().st_size == 0:
        return None
    return FrameArtifact(
        path=destination,
        timestamp_seconds=round(timestamp, 3),
        kind='keyframe',
        size_bytes=destination.stat().st_size,
    )


def extract_keyframes(path: Path, out_dir: Path, limit: int | None = None) -> list[FrameArtifact]:
    out_dir.mkdir(parents=True, exist_ok=True)
    frames: list[FrameArtifact] = []
    for index, timestamp in enumerate(keyframe_timestamps(path, limit)):
        frame = extract_frame_at(path, timestamp, out_dir / f'keyframe-{index:03d}.jpg')
        if frame:
            frames.append(frame)
    return frames


SCENE_LINE = re.compile(r'pts_time:([0-9.]+)')
SCENE_SCORE = re.compile(r'lavfi\.scene_score=([0-9.]+)')


def detect_scene_changes(path: Path, threshold: float | None = None) -> list[SceneChange]:
    """Return timestamps where the visual scene changes above the threshold."""
    level = threshold if threshold is not None else settings.scene_change_threshold
    result = _run(
        [
            ffmpeg_binary(), '-v', 'info', '-i', str(path),
            '-filter_complex', f"select='gt(scene,{level})',metadata=print:file=-",
            '-an', '-f', 'null', '-',
        ],
        timeout=settings.ffmpeg_timeout_seconds,
        allow_failure=True,
    )
    output = (result.stdout or '') + '\n' + (result.stderr or '')
    scenes: list[SceneChange] = []
    pending: float | None = None
    for line in output.splitlines():
        stamp = SCENE_LINE.search(line)
        if stamp:
            pending = round(float(stamp.group(1)), 3)
        score = SCENE_SCORE.search(line)
        if score and pending is not None:
            scenes.append(SceneChange(timestamp_seconds=pending, score=round(float(score.group(1)), 4)))
            pending = None
    return scenes


SILENCE_START = re.compile(r'silence_start: (-?[0-9.]+)')
SILENCE_END = re.compile(r'silence_end: (-?[0-9.]+)')


def detect_silence(path: Path, noise_db: int | None = None, min_seconds: float | None = None) -> list[SilenceWindow]:
    """Return silence windows using FFmpeg ``silencedetect``."""
    noise = noise_db if noise_db is not None else settings.silence_noise_db
    minimum = min_seconds if min_seconds is not None else settings.silence_min_seconds
    result = _run(
        [
            ffmpeg_binary(), '-v', 'info', '-i', str(path),
            '-af', f'silencedetect=noise={noise}dB:d={minimum}', '-f', 'null', '-',
        ],
        timeout=settings.ffmpeg_timeout_seconds,
        allow_failure=True,
    )
    stderr = result.stderr or ''
    windows: list[SilenceWindow] = []
    start: float | None = None
    for line in stderr.splitlines():
        begin = SILENCE_START.search(line)
        if begin:
            start = max(0.0, float(begin.group(1)))
        finish = SILENCE_END.search(line)
        if finish and start is not None:
            windows.append(SilenceWindow(start_seconds=round(start, 3), end_seconds=round(float(finish.group(1)), 3)))
            start = None
    return windows


def extract_thumbnails(path: Path, out_dir: Path, duration: float | None, count: int | None = None) -> list[FrameArtifact]:
    """Extract cover candidates: an early frame plus evenly spaced positions."""
    total = count or settings.thumbnail_candidates
    out_dir.mkdir(parents=True, exist_ok=True)
    span = duration or 0.0
    positions = [0.4] if span <= 1 else [min(0.6, span / 10)] + [
        round(span * ratio, 3) for ratio in (0.25, 0.5, 0.75)[: max(0, total - 1)]
    ]
    candidates: list[FrameArtifact] = []
    for index, timestamp in enumerate(positions[:total]):
        frame = extract_frame_at(path, timestamp, out_dir / f'thumbnail-{index:02d}.jpg', width=720)
        if frame:
            candidates.append(
                FrameArtifact(
                    path=frame.path,
                    timestamp_seconds=frame.timestamp_seconds,
                    kind='thumbnail',
                    size_bytes=frame.size_bytes,
                )
            )
    # Larger JPEG size at equal settings means more detail/contrast: used only to
    # order candidates for a human editor, never as an "AI verified" claim.
    return sorted(candidates, key=lambda item: item.size_bytes, reverse=True)


# --------------------------------------------------------------------------- orchestration
def analyze_media(path: Path, workdir: Path, *, deep: bool = False) -> MediaBundle:
    """Run the full measured media pipeline for one video file."""
    workdir.mkdir(parents=True, exist_ok=True)
    media = probe(path, deep=deep)
    assert_playable(media)

    bundle = MediaBundle(probe=media, tool_versions=tool_versions())
    if media.has_audio:
        try:
            bundle.audio = extract_audio(path, workdir / 'audio.wav')
            bundle.silences = detect_silence(path)
        except MediaError as error:
            logger.warning('audio stage degraded', extra={'error_code': getattr(error, 'code', 'media_error')})
    bundle.frames = sample_frames(path, workdir / 'frames')
    bundle.keyframes = extract_keyframes(path, workdir / 'keyframes')
    bundle.scene_changes = detect_scene_changes(path)
    bundle.thumbnails = extract_thumbnails(path, workdir / 'thumbnails', media.duration_seconds)
    logger.info(
        'media pipeline complete',
        extra={
            'duration_seconds': media.duration_seconds,
            'frames': len(bundle.frames),
            'keyframes': len(bundle.keyframes),
            'scene_changes': len(bundle.scene_changes),
            'silence_seconds': bundle.silence_seconds,
        },
    )
    return bundle


def timeline_seconds(duration: float | None) -> int:
    if not duration or duration <= 0:
        return 0
    return int(math.ceil(min(duration, settings.max_duration_seconds)))
