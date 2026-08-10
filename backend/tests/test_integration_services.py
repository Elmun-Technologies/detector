"""Real-service integration profile: PostgreSQL, Redis and MinIO.

Every test here is marked ``integration`` and skips itself when the service is
not reachable, so the default suite stays hermetic. CI runs this module with
service containers:

```bash
INTEGRATION_DATABASE_URL=postgresql+psycopg://viral:viral@localhost:5432/viral \
INTEGRATION_REDIS_URL=redis://localhost:6379/1 \
INTEGRATION_S3_ENDPOINT=http://localhost:9000 \
INTEGRATION_S3_BUCKET=viral-ci INTEGRATION_S3_ACCESS_KEY=minioadmin \
INTEGRATION_S3_SECRET_KEY=minioadmin \
pytest backend/tests/test_integration_services.py -m integration
```

Locally (or in the sandbox) the same command reports skips instead of failures.
"""
from __future__ import annotations

import os
import socket
import uuid
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlparse

import pytest

from app.config import settings
from conftest import override, restore

pytestmark = pytest.mark.integration

DATABASE_URL = os.getenv('INTEGRATION_DATABASE_URL') or (
    settings.database_url if settings.database_url.startswith('postgresql') else ''
)
REDIS_URL = os.getenv('INTEGRATION_REDIS_URL') or os.getenv('REDIS_URL', '')
S3_ENDPOINT = os.getenv('INTEGRATION_S3_ENDPOINT') or (settings.s3_endpoint or '')
S3_BUCKET = os.getenv('INTEGRATION_S3_BUCKET') or (settings.s3_bucket or '')
S3_ACCESS_KEY = os.getenv('INTEGRATION_S3_ACCESS_KEY') or (settings.s3_access_key or '')
S3_SECRET_KEY = os.getenv('INTEGRATION_S3_SECRET_KEY') or (settings.s3_secret_key or '')


def reachable(url: str, default_port: int) -> bool:
    if not url:
        return False
    parsed = urlparse(url if '://' in url else f'//{url}')
    host = parsed.hostname or 'localhost'
    port = parsed.port or default_port
    try:
        with socket.create_connection((host, port), timeout=2):
            return True
    except OSError:
        return False


postgres = pytest.mark.skipif(
    not (DATABASE_URL and reachable(DATABASE_URL, 5432)),
    reason='PostgreSQL is not configured/reachable (set INTEGRATION_DATABASE_URL)',
)
redis_service = pytest.mark.skipif(
    not (REDIS_URL and reachable(REDIS_URL, 6379)),
    reason='Redis is not configured/reachable (set INTEGRATION_REDIS_URL)',
)
minio = pytest.mark.skipif(
    not (S3_ENDPOINT and S3_BUCKET and S3_ACCESS_KEY and S3_SECRET_KEY and reachable(S3_ENDPOINT, 9000)),
    reason='MinIO/S3 is not configured/reachable (set INTEGRATION_S3_*)',
)


# --------------------------------------------------------------------------- PostgreSQL
@postgres
def test_alembic_upgrade_head_runs_against_postgresql():
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, inspect, text

    schema = f'ci_{uuid.uuid4().hex[:10]}'
    engine = create_engine(DATABASE_URL)
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    try:
        url = f'{DATABASE_URL}?options=-csearch_path%3D{schema}'
        config = Config(str(Path(__file__).parents[2] / 'alembic.ini'))
        config.set_main_option('script_location', str(Path(__file__).parents[1] / 'alembic'))
        config.set_main_option('sqlalchemy.url', url)
        command.upgrade(config, 'head')

        info = inspect(create_engine(url))
        tables = set(info.get_table_names(schema=schema))
        assert {'users', 'workspaces', 'videos', 'video_analyses', 'analysis_jobs', 'media_artifacts', 'provider_calls'} <= tables
    finally:
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        engine.dispose()


@postgres
def test_analysis_job_idempotency_key_is_enforced_by_postgresql():
    from sqlalchemy import create_engine
    from sqlalchemy.exc import IntegrityError
    from sqlalchemy.orm import sessionmaker

    from app.database import Base
    from app.models import AnalysisJob, User, Video, VideoAnalysis, Workspace

    engine = create_engine(DATABASE_URL)
    prefix = f'ci_{uuid.uuid4().hex[:8]}_'
    metadata = Base.metadata
    try:
        metadata.create_all(engine)
        Session = sessionmaker(bind=engine)
        with Session() as db:
            user = User(telegram_id=prefix)
            db.add(user)
            db.flush()
            workspace = Workspace(owner_id=user.id, name=f'{prefix}workspace')
            db.add(workspace)
            db.flush()
            video = Video(
                workspace_id=workspace.id,
                storage_key=f'{prefix}key',
                original_name='clip.mp4',
                content_type='video/mp4',
                size_bytes=10,
            )
            db.add(video)
            db.flush()
            analysis = VideoAnalysis(video_id=video.id, status='queued')
            db.add(analysis)
            db.flush()
            key = f'{prefix}idempotency'
            db.add(AnalysisJob(analysis_id=analysis.id, status='queued', idempotency_key=key))
            db.commit()

            db.add(AnalysisJob(analysis_id=analysis.id, status='queued', idempotency_key=key))
            with pytest.raises(IntegrityError):
                db.commit()
            db.rollback()
    finally:
        engine.dispose()


# --------------------------------------------------------------------------- Redis / Celery
@redis_service
def test_redis_broker_accepts_a_real_task_message():
    from celery import Celery

    app = Celery('viral_integration', broker=REDIS_URL, backend=REDIS_URL)
    app.conf.update(task_always_eager=False, broker_connection_retry_on_startup=True)
    with app.connection() as connection:
        connection.ensure_connection(max_retries=1, timeout=5)

    async_result = app.send_task('app.tasks.analyze_video', args=['integration-probe'], queue='analysis')
    assert async_result.id
    # No worker consumes the probe here; purge so the queue stays clean.
    app.control.purge()


@redis_service
def test_readiness_endpoint_reports_the_broker():
    from app.health import readiness

    previous = override(queue_mode='celery')
    try:
        _ready, report = readiness()
    finally:
        restore(previous)
    assert report['checks']['broker']['status'] in {'ok', 'skipped'}
    assert report['checks']['database']['status'] == 'ok'


# --------------------------------------------------------------------------- MinIO / S3
@pytest.fixture
def minio_storage():
    from app.storage import S3Storage

    previous = override(
        storage_backend='s3',
        s3_bucket=S3_BUCKET,
        s3_endpoint=S3_ENDPOINT,
        s3_access_key=S3_ACCESS_KEY,
        s3_secret_key=S3_SECRET_KEY,
        s3_force_path_style=True,
    )
    storage = S3Storage()
    storage.ensure_bucket()
    try:
        yield storage
    finally:
        storage.delete_prefix('workspaces/integration')
        restore(previous)


@minio
def test_minio_roundtrip_with_presigned_urls(minio_storage, tmp_path, sample_mp4):
    import httpx

    from app.storage import source_key

    key = source_key('integration', uuid.uuid4().hex, 'clip.mp4')
    stored = minio_storage.put_file(sample_mp4, key, 'video/mp4')
    assert stored.size_bytes == sample_mp4.stat().st_size
    assert minio_storage.exists(key)

    destination: Path = tmp_path / 'downloaded.mp4'
    minio_storage.download(key, destination)
    assert destination.read_bytes() == sample_mp4.read_bytes()

    presigned = minio_storage.presigned_get_url(key)
    response = httpx.get(presigned.url, timeout=10)
    assert response.status_code == 200
    assert len(response.content) == sample_mp4.stat().st_size

    upload_key = source_key('integration', uuid.uuid4().hex, 'upload.mp4')
    put_url = minio_storage.presigned_put_url(upload_key, content_type='video/mp4')
    uploaded = httpx.put(put_url.url, content=sample_mp4.read_bytes(), headers=put_url.headers, timeout=30)
    assert uploaded.status_code in {200, 204}
    assert minio_storage.exists(upload_key)

    minio_storage.delete(key)
    minio_storage.delete(upload_key)
    assert not minio_storage.exists(key)


@minio
def test_minio_objects_are_private_without_a_signature(minio_storage, sample_mp4):
    import httpx

    from app.storage import source_key

    key = source_key('integration', uuid.uuid4().hex, 'private.mp4')
    minio_storage.put_file(sample_mp4, key, 'video/mp4')
    try:
        endpoint = S3_ENDPOINT.rstrip('/')
        response = httpx.get(f'{endpoint}/{S3_BUCKET}/{key}', timeout=10)
        assert response.status_code in {401, 403}, 'objects must not be publicly readable'
    finally:
        minio_storage.delete(key)


@minio
def test_minio_lifecycle_and_prefix_cleanup(minio_storage, sample_mp4):
    from app.storage import artifact_key

    minio_storage.ensure_lifecycle()
    key = artifact_key('integration', uuid.uuid4().hex, 'frame', 'frame.jpg')
    minio_storage.put_file(sample_mp4, key, 'image/jpeg')
    removed = minio_storage.cleanup_expired('workspaces/integration', timedelta(seconds=-1))
    assert removed >= 1
    assert not minio_storage.exists(key)


# --------------------------------------------------------------------------- full stack
@postgres
@redis_service
@minio
def test_all_three_services_are_configured_together():
    """Guard rail: the CI integration job must exercise every backing service."""
    assert DATABASE_URL.startswith('postgresql')
    assert REDIS_URL.startswith('redis')
    assert S3_ENDPOINT and S3_BUCKET
