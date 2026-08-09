"""Media artifact retention.

Derived media (audio, frames, keyframes, thumbnails) is temporary. It must be
deleted from private storage and marked deleted in the database once its
retention window closes, working directories must not survive a task, and the
S3 backend must additionally carry a server-side lifecycle policy.
"""
from __future__ import annotations

import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app import analysis_service
from app.config import settings
from app.models import MediaArtifact, Video
from app.pipeline import cleanup_expired_artifacts, purge_video_objects
from app.schemas import VideoContext
from app.storage import artifact_key, get_storage, source_key
from app.tasks import analyze_video
from app.tasks import cleanup_expired_artifacts as cleanup_task
from conftest import override, restore, workspace_fixture


def stage(session, tmp_path, sample_mp4, suffix='cleanup'):
    _user_id, workspace_id = workspace_fixture(session)
    copy = tmp_path / f'clip-{suffix}.mp4'
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
    analysis, job = analysis_service.create_analysis(session, video, VideoContext(), f'{workspace_id}:{suffix}')
    session.commit()
    return workspace_id, video, analysis.id, job.id


def make_artifact(session, video, *, kind='frame', expires_in_hours=-1, payload=b'artifact-bytes'):
    storage = get_storage()
    key = artifact_key(video.workspace_id, video.id, kind, f'{kind}.bin')
    with tempfile.NamedTemporaryFile(delete=False) as handle:
        handle.write(payload)
        temporary = Path(handle.name)
    try:
        stored = storage.put_file(temporary, key, 'application/octet-stream')
    finally:
        temporary.unlink(missing_ok=True)
    artifact = MediaArtifact(
        video_id=video.id,
        kind=kind,
        storage_key=stored.key,
        content_type='application/octet-stream',
        size_bytes=stored.size_bytes,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=expires_in_hours),
    )
    session.add(artifact)
    session.commit()
    return artifact


def test_pipeline_registers_every_artifact_with_an_expiry(session, tmp_path, sample_mp4, media_tools):
    _workspace, video, analysis_id, _job = stage(session, tmp_path, sample_mp4)
    analyze_video.delay(analysis_id).get()
    session.expire_all()

    artifacts = session.query(MediaArtifact).filter_by(video_id=video.id).all()
    assert artifacts, 'the pipeline must register its derived media'
    horizon = datetime.now(timezone.utc) + timedelta(hours=settings.artifact_retention_hours + 1)
    for artifact in artifacts:
        expires = artifact.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        assert expires <= horizon
        assert artifact.deleted_at is None
        assert get_storage().exists(artifact.storage_key)


def test_expired_artifacts_are_deleted_from_storage_and_marked_in_the_database(session, tmp_path, sample_mp4):
    _workspace, video, _analysis_id, _job = stage(session, tmp_path, sample_mp4, suffix='expired')
    expired = make_artifact(session, video, kind='frame', expires_in_hours=-1)
    live = make_artifact(session, video, kind='thumbnail', expires_in_hours=+6)
    storage = get_storage()

    removed = cleanup_expired_artifacts(session)

    session.expire_all()
    assert removed == 1
    assert storage.exists(expired.storage_key) is False
    assert storage.exists(live.storage_key) is True
    assert session.get(MediaArtifact, expired.id).deleted_at is not None
    assert session.get(MediaArtifact, live.id).deleted_at is None
    # The source upload is never touched by artifact cleanup.
    assert storage.exists(session.get(Video, video.id).storage_key) is True


def test_cleanup_is_idempotent_and_runs_as_a_celery_task(session, tmp_path, sample_mp4):
    _workspace, video, _analysis_id, _job = stage(session, tmp_path, sample_mp4, suffix='task')
    make_artifact(session, video, expires_in_hours=-2)

    assert cleanup_task.delay().get() == 1
    assert cleanup_task.delay().get() == 0, 'already deleted artifacts must not be deleted twice'


def test_cleanup_survives_an_object_that_is_already_gone(session, tmp_path, sample_mp4):
    _workspace, video, _analysis_id, _job = stage(session, tmp_path, sample_mp4, suffix='missing')
    artifact = make_artifact(session, video, expires_in_hours=-3)
    get_storage().delete(artifact.storage_key)

    assert cleanup_expired_artifacts(session) == 1
    session.expire_all()
    assert session.get(MediaArtifact, artifact.id).deleted_at is not None


def test_working_directories_do_not_survive_the_worker(session, tmp_path, sample_mp4, media_tools):
    _workspace, _video, analysis_id, _job = stage(session, tmp_path, sample_mp4, suffix='workdir')
    before = set(Path(tempfile.gettempdir()).glob('viral-*'))
    analyze_video.delay(analysis_id).get()
    assert set(Path(tempfile.gettempdir()).glob('viral-*')) == before


def test_purge_removes_source_and_artifacts_for_erasure(session, tmp_path, sample_mp4):
    _workspace, video, _analysis_id, _job = stage(session, tmp_path, sample_mp4, suffix='purge')
    artifact = make_artifact(session, video, expires_in_hours=+12)
    storage = get_storage()

    removed = purge_video_objects(session, video)

    session.expire_all()
    assert removed >= 2
    assert storage.exists(artifact.storage_key) is False
    assert storage.exists(video.storage_key) is False
    assert session.get(MediaArtifact, artifact.id).deleted_at is not None


def test_local_backend_supports_prefix_expiry_sweeps(session, tmp_path, sample_mp4):
    _workspace, video, _analysis_id, _job = stage(session, tmp_path, sample_mp4, suffix='sweep')
    artifact = make_artifact(session, video, expires_in_hours=-1)
    storage = get_storage()

    swept = storage.cleanup_expired(f'workspaces/{video.workspace_id}', timedelta(seconds=-1))

    assert swept >= 1
    assert storage.exists(artifact.storage_key) is False


def test_s3_backend_publishes_a_server_side_lifecycle_policy():
    boto3 = pytest.importorskip('boto3')
    moto = pytest.importorskip('moto')
    from app.storage import S3Storage

    with moto.mock_aws():
        previous = override(
            storage_backend='s3',
            s3_bucket='viral-lifecycle-bucket',
            s3_endpoint=None,
            s3_access_key='test-access',
            s3_secret_key='test-secret',
            s3_region='us-east-1',
        )
        try:
            storage = S3Storage()
            storage.ensure_bucket()
            storage.ensure_lifecycle()
            client = boto3.client('s3', region_name='us-east-1')
            rules = client.get_bucket_lifecycle_configuration(Bucket='viral-lifecycle-bucket')['Rules']
            ids = {rule['ID'] for rule in rules}
            assert 'viral-temp-artifacts' in ids
            assert 'viral-analysis-artifacts' in ids
            assert all(rule['Status'] == 'Enabled' for rule in rules)
        finally:
            restore(previous)
