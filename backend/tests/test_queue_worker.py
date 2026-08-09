"""Queue and worker semantics: idempotency, retries, failure states, recovery."""
from __future__ import annotations

import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app import analysis_service, pipeline as pipeline_module
from app.models import AnalysisJob, MediaArtifact, ProviderCall, Video, VideoAnalysis
from app.providers import ProviderConfigurationError
from app.schemas import VideoContext
from app.storage import StorageTransientError, get_storage, source_key
from app.tasks import analyze_video, recover_stuck_jobs, retry_countdown, should_retry
from conftest import auth_header, override, restore, workspace_fixture


def stage_video(session, tmp_path: Path, sample_mp4: Path, *, key_suffix: str = 'a'):
    user_id, workspace_id = workspace_fixture(session)
    copy = tmp_path / f'clip-{key_suffix}.mp4'
    copy.write_bytes(sample_mp4.read_bytes())
    video = Video(
        workspace_id=workspace_id,
        storage_key='pending',
        original_name='clip.mp4',
        content_type='video/mp4',
        size_bytes=copy.stat().st_size,
        status='queued',
        storage_backend='local',
    )
    session.add(video)
    session.flush()
    stored = get_storage().put_file(copy, source_key(workspace_id, video.id, 'clip.mp4'), 'video/mp4')
    video.storage_key = stored.key
    analysis, job = analysis_service.create_analysis(
        session,
        video,
        VideoContext(title='Queue test', account={'account_type': 'expert', 'average_views': 8000}),
        f'{workspace_id}:{key_suffix}',
    )
    session.commit()
    return user_id, workspace_id, video.id, analysis.id, job.id


def test_backoff_helpers_are_exponential_and_capped():
    assert retry_countdown(1) < retry_countdown(2) < retry_countdown(3)
    previous = override(task_retry_backoff_seconds=10, task_retry_backoff_max_seconds=100)
    try:
        assert retry_countdown(1) == 10
        assert retry_countdown(2) == 20
        assert retry_countdown(9) == 100
    finally:
        restore(previous)
    assert should_retry(True, 1, 3) is True
    assert should_retry(True, 3, 3) is False
    assert should_retry(False, 1, 3) is False


def test_pipeline_completes_and_persists_artifacts(session, tmp_path, sample_mp4, media_tools):
    _user, _workspace, video_id, analysis_id, job_id = stage_video(session, tmp_path, sample_mp4)
    before = set(Path(tempfile.gettempdir()).glob('viral-*'))

    result = analyze_video.delay(analysis_id).get()

    session.expire_all()
    analysis = session.get(VideoAnalysis, analysis_id)
    job = session.get(AnalysisJob, job_id)
    assert result['status'] == 'completed'
    assert analysis.status == 'completed'
    assert analysis.report['scores']['viral_score'] >= 0
    assert analysis.report['media']['analysed'] is True
    assert analysis.report['media']['scene_change_count'] >= 1
    assert analysis.report['timeline'], 'second-by-second timeline must exist'
    assert job.status == 'completed' and job.progress == 100

    artifacts = session.query(MediaArtifact).filter_by(video_id=video_id).all()
    kinds = {artifact.kind for artifact in artifacts}
    assert {'audio', 'frame', 'keyframe', 'thumbnail'} <= kinds
    assert all(artifact.expires_at is not None for artifact in artifacts)
    storage = get_storage()
    assert all(storage.exists(artifact.storage_key) for artifact in artifacts)

    # Temporary working directories must not survive the task.
    assert set(Path(tempfile.gettempdir()).glob('viral-*')) == before


def test_completed_job_is_not_recomputed_on_redelivery(session, tmp_path, sample_mp4):
    _user, _workspace, _video, analysis_id, _job = stage_video(session, tmp_path, sample_mp4)
    analyze_video.delay(analysis_id).get()
    session.expire_all()
    first = session.get(VideoAnalysis, analysis_id).report['generated_at']

    replay = analyze_video.delay(analysis_id).get()

    session.expire_all()
    assert replay.get('idempotent') is True
    assert session.get(VideoAnalysis, analysis_id).report['generated_at'] == first


def test_upload_idempotency_key_reuses_the_same_analysis(client, session, sample_mp4):
    user_id, workspace_id = workspace_fixture(session)
    headers = {**auth_header(user_id), 'Idempotency-Key': 'client-key-1'}
    payload = {'file': ('clip.mp4', sample_mp4.read_bytes(), 'video/mp4')}

    first = client.post(f'/v1/workspaces/{workspace_id}/videos/upload', files=payload, data={'context': '{}'}, headers=headers)
    second = client.post(f'/v1/workspaces/{workspace_id}/videos/upload', files=payload, data={'context': '{}'}, headers=headers)

    assert first.status_code == 202 and second.status_code == 202
    assert first.json()['idempotent'] is False
    assert second.json()['idempotent'] is True
    assert first.json()['analysis_id'] == second.json()['analysis_id']
    assert session.query(AnalysisJob).count() == 1
    assert session.query(VideoAnalysis).count() == 1


def test_transient_storage_failure_retries_then_fails(session, tmp_path, sample_mp4, monkeypatch):
    _user, _workspace, _video, analysis_id, job_id = stage_video(session, tmp_path, sample_mp4)
    job = session.get(AnalysisJob, job_id)
    job.max_attempts = 2
    session.commit()

    attempts = {'count': 0}

    class FlakyStorage:
        def download(self, *_args, **_kwargs):
            attempts['count'] += 1
            raise StorageTransientError('MinIO is unreachable')

    monkeypatch.setattr(pipeline_module, 'get_storage', lambda: FlakyStorage())

    with pytest.raises(Exception):
        analyze_video.delay(analysis_id).get()

    session.expire_all()
    job = session.get(AnalysisJob, job_id)
    analysis = session.get(VideoAnalysis, analysis_id)
    assert attempts['count'] >= 2, 'the transient failure must be retried'
    assert job.attempts == 2
    assert job.status == 'failed'
    assert job.error_code == 'storage_unavailable'
    assert analysis.status == 'failed'


def test_provider_configuration_error_fails_without_retry(session, tmp_path, sample_mp4):
    _user, _workspace, _video, analysis_id, job_id = stage_video(session, tmp_path, sample_mp4)
    previous = override(allow_demo_providers=False, openai_api_key=None)
    try:
        with pytest.raises(ProviderConfigurationError):
            analyze_video.delay(analysis_id).get()
    finally:
        restore(previous)

    session.expire_all()
    job = session.get(AnalysisJob, job_id)
    analysis = session.get(VideoAnalysis, analysis_id)
    assert job.attempts == 1, 'a configuration error must not be retried'
    assert job.status == 'failed'
    assert job.error_code == 'provider_not_configured'
    assert analysis.status == 'failed'
    assert analysis.report is None, 'no fabricated report may be persisted'


def test_corrupted_media_fails_permanently(session, tmp_path, media_tools):
    user_id, workspace_id = workspace_fixture(session)
    broken = tmp_path / 'broken.mp4'
    broken.write_bytes(b'\x00\x00\x00\x18ftypmp42' + b'garbage' * 20)
    video = Video(
        workspace_id=workspace_id,
        storage_key='pending',
        original_name='broken.mp4',
        content_type='video/mp4',
        size_bytes=broken.stat().st_size,
        status='queued',
    )
    session.add(video)
    session.flush()
    stored = get_storage().put_file(broken, source_key(workspace_id, video.id, 'broken.mp4'), 'video/mp4')
    video.storage_key = stored.key
    analysis, job = analysis_service.create_analysis(session, video, VideoContext(), f'{workspace_id}:broken')
    session.commit()

    with pytest.raises(Exception):
        analyze_video.delay(analysis.id).get()

    session.expire_all()
    assert session.get(AnalysisJob, job.id).error_code == 'media_corrupted'
    assert session.get(AnalysisJob, job.id).attempts == 1
    assert session.get(VideoAnalysis, analysis.id).status == 'failed'


def test_cancel_stops_execution(session, tmp_path, sample_mp4):
    _user, _workspace, _video, analysis_id, job_id = stage_video(session, tmp_path, sample_mp4)
    analysis_service.request_cancel(session, analysis_id)

    result = analyze_video.delay(analysis_id).get()

    session.expire_all()
    assert result['status'] == 'cancelled'
    assert session.get(AnalysisJob, job_id).status == 'cancelled'
    assert session.get(VideoAnalysis, analysis_id).status == 'cancelled'


def test_cancel_retry_and_progress_endpoints(client, session, sample_mp4):
    user_id, workspace_id = workspace_fixture(session)
    headers = auth_header(user_id)
    upload = client.post(
        f'/v1/workspaces/{workspace_id}/videos/upload',
        files={'file': ('clip.mp4', sample_mp4.read_bytes(), 'video/mp4')},
        data={'context': '{}'},
        headers=headers,
    )
    analysis_id = upload.json()['analysis_id']

    progress = client.get(f'/v1/analyses/{analysis_id}/progress', headers=headers)
    assert progress.status_code == 200
    body = progress.json()
    assert body['analysis_id'] == analysis_id
    assert body['progress'] == 100 and body['status'] == 'completed'

    cancel = client.post(f'/v1/analyses/{analysis_id}/cancel', headers=headers)
    assert cancel.status_code == 200 and cancel.json()['cancel_requested'] is True

    retry = client.post(f'/v1/analyses/{analysis_id}/retry', headers=headers)
    assert retry.status_code == 202
    session.expire_all()
    assert session.get(VideoAnalysis, analysis_id).status == 'completed'


def test_worker_restart_recovers_abandoned_jobs(session, tmp_path, sample_mp4):
    _user, _workspace, _video, analysis_id, job_id = stage_video(session, tmp_path, sample_mp4, key_suffix='recover')
    job = session.get(AnalysisJob, job_id)
    job.status = 'running'
    job.attempts = 1
    job.heartbeat_at = datetime.now(timezone.utc) - timedelta(hours=2)
    session.commit()

    recovered = recover_stuck_jobs(timeout_seconds=60)

    session.expire_all()
    assert recovered == 1
    assert session.get(AnalysisJob, job_id).status == 'completed'
    assert session.get(VideoAnalysis, analysis_id).status == 'completed'


def test_exhausted_jobs_are_marked_failed_by_recovery(session, tmp_path, sample_mp4):
    _user, _workspace, _video, analysis_id, job_id = stage_video(session, tmp_path, sample_mp4, key_suffix='dead')
    job = session.get(AnalysisJob, job_id)
    job.status = 'running'
    job.attempts = job.max_attempts
    job.heartbeat_at = datetime.now(timezone.utc) - timedelta(hours=2)
    session.commit()

    assert recover_stuck_jobs(timeout_seconds=60) == 0

    session.expire_all()
    assert session.get(AnalysisJob, job_id).status == 'failed'
    assert session.get(AnalysisJob, job_id).error_code == 'worker_lost'
    assert session.get(VideoAnalysis, analysis_id).status == 'failed'


def test_provider_usage_is_recorded_per_analysis(session, tmp_path, sample_mp4, media_tools):
    _user, _workspace, _video, analysis_id, _job = stage_video(session, tmp_path, sample_mp4, key_suffix='usage')
    analyze_video.delay(analysis_id).get()
    session.expire_all()
    calls = session.query(ProviderCall).filter_by(analysis_id=analysis_id).all()
    # Demo mode records the demo STT/LLM calls; production records real usage.
    assert all(call.mode in {'demo', 'production'} for call in calls)
    assert session.get(VideoAnalysis, analysis_id).cost_usd is not None
