"""FFmpeg/FFprobe pipeline tests against a real MP4 fixture.

The fixture is a 6 second 240x426 H.264/AAC vertical clip built from three
2-second scenes where the middle two seconds are silent, so scene-change and
silence detection have something real to find.
"""
from __future__ import annotations

import shutil

import pytest

from app import media
from app.config import settings


def test_probe_reports_codec_duration_resolution_and_audio(sample_mp4, media_tools):
    probe = media.probe(sample_mp4)

    assert probe.video_codec == 'h264'
    assert probe.audio_codec == 'aac'
    assert probe.has_audio is True
    assert probe.width == 240 and probe.height == 426
    assert probe.aspect_ratio == '9:16'  # 240x426 snaps to the vertical standard
    assert probe.aspect_ratio_value == pytest.approx(240 / 426, rel=1e-3)
    assert probe.is_vertical is True
    assert probe.duration_seconds == pytest.approx(6.0, abs=0.3)
    assert probe.fps == pytest.approx(10.0, abs=0.5)
    assert probe.corrupt is False
    assert 'no_audio_track' not in probe.warnings


def test_truncated_file_is_detected_as_corrupted(sample_mp4, tmp_path, media_tools):
    broken = tmp_path / 'broken.mp4'
    broken.write_bytes(sample_mp4.read_bytes()[:1200])
    with pytest.raises(media.MediaCorruptedError):
        media.probe(broken)


def test_empty_and_missing_files_are_rejected(tmp_path, media_tools):
    empty = tmp_path / 'empty.mp4'
    empty.write_bytes(b'')
    with pytest.raises(media.MediaCorruptedError):
        media.probe(empty)
    with pytest.raises(media.MediaValidationError):
        media.probe(tmp_path / 'nope.mp4')


def test_audio_extraction_produces_mono_pcm(sample_mp4, tmp_path, media_tools):
    artifact = media.extract_audio(sample_mp4, tmp_path / 'audio.wav')
    assert artifact.path.exists() and artifact.size_bytes > 1000
    assert artifact.channels == 1
    assert artifact.sample_rate == settings.audio_sample_rate
    assert artifact.duration_seconds == pytest.approx(6.0, abs=0.5)


def test_frame_and_keyframe_sampling(sample_mp4, tmp_path, media_tools):
    frames = media.sample_frames(sample_mp4, tmp_path / 'frames', interval_seconds=1.0, limit=6)
    assert 3 <= len(frames) <= 6
    assert all(frame.path.exists() and frame.size_bytes > 0 for frame in frames)
    assert frames[1].timestamp_seconds > frames[0].timestamp_seconds

    keyframes = media.extract_keyframes(sample_mp4, tmp_path / 'keyframes', limit=4)
    assert keyframes and all(frame.kind == 'keyframe' for frame in keyframes)


def test_scene_change_and_silence_detection(sample_mp4, media_tools):
    scenes = media.detect_scene_changes(sample_mp4, threshold=0.2)
    assert scenes, 'expected at least one scene change in the three-scene fixture'
    assert all(0 <= scene.timestamp_seconds <= 6.5 for scene in scenes)

    silences = media.detect_silence(sample_mp4, noise_db=-40, min_seconds=0.3)
    assert silences, 'expected the silent middle segment to be detected'
    total = sum(window.duration_seconds for window in silences)
    assert total == pytest.approx(2.0, abs=0.6)


def test_thumbnail_candidates_are_extracted_and_ordered(sample_mp4, tmp_path, media_tools):
    candidates = media.extract_thumbnails(sample_mp4, tmp_path / 'thumbs', duration=6.0, count=3)
    assert 1 <= len(candidates) <= 3
    assert all(candidate.kind == 'thumbnail' for candidate in candidates)
    assert candidates == sorted(candidates, key=lambda item: item.size_bytes, reverse=True)


def test_analyze_media_returns_full_bundle(sample_mp4, tmp_path, media_tools):
    bundle = media.analyze_media(sample_mp4, tmp_path / 'work')

    assert bundle.probe.duration_seconds == pytest.approx(6.0, abs=0.3)
    assert bundle.audio is not None
    assert bundle.frames and bundle.keyframes and bundle.thumbnails
    assert bundle.scene_changes
    assert bundle.silence_seconds > 0
    assert 0 < (bundle.speech_ratio or 0) < 1

    metadata = bundle.to_metadata()
    assert metadata['video_codec'] == 'h264'
    assert metadata['scene_change_count' if 'scene_change_count' in metadata else 'scene_change_rate'] is not None
    assert metadata['tool_versions']['ffmpeg'] != 'unavailable'


def test_missing_binary_raises_tool_unavailable(monkeypatch, sample_mp4):
    monkeypatch.setattr(shutil, 'which', lambda _name: None)
    from conftest import override, restore

    previous = override(ffprobe_binary='definitely-not-installed', ffmpeg_binary='definitely-not-installed')
    try:
        with pytest.raises(media.MediaToolUnavailableError):
            media.probe(sample_mp4)
        assert media.tools_available() is False
    finally:
        restore(previous)
