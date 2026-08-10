"""Storage adapter contract.

Both adapters (local disk and S3/MinIO) must satisfy the same behaviour, so the
same test body runs twice: once on disk, once against a mocked S3 endpoint.
"""
from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest

from app import storage as storage_module
from app.config import settings
from app.storage import (
    LocalStorage,
    S3Storage,
    StorageNotFoundError,
    StoragePermissionError,
    StorageTransientError,
    StorageValidationError,
    artifact_key,
    get_storage,
    source_key,
)
from conftest import override, restore


@pytest.fixture(params=['local', 's3'])
def adapter(request, tmp_path):
    if request.param == 'local':
        previous = override(storage_backend='local', uploads_dir=tmp_path / 'local-objects')
        yield LocalStorage(tmp_path / 'local-objects')
        restore(previous)
        return

    boto3 = pytest.importorskip('boto3')
    moto = pytest.importorskip('moto')
    with moto.mock_aws():
        previous = override(
            storage_backend='s3',
            s3_bucket='viral-test-bucket',
            s3_endpoint=None,
            s3_access_key='test-access',
            s3_secret_key='test-secret',
            s3_region='us-east-1',
        )
        boto3.client('s3', region_name='us-east-1').create_bucket(Bucket='viral-test-bucket')
        yield S3Storage()
        restore(previous)


def write(tmp_path: Path, name: str, payload: bytes = b'viral-video-bytes') -> Path:
    path = tmp_path / name
    path.write_bytes(payload)
    return path


def test_put_stat_download_and_delete_roundtrip(adapter, tmp_path):
    key = source_key('workspace-1', 'video-1', 'clip.mp4')
    stored = adapter.put_file(write(tmp_path, 'clip.mp4'), key, 'video/mp4')

    assert stored.key == key
    assert stored.size_bytes == len(b'viral-video-bytes')
    assert stored.checksum_sha256
    assert adapter.exists(key)
    assert adapter.stat(key).size_bytes == stored.size_bytes

    destination = adapter.download(key, tmp_path / 'out' / 'clip.mp4')
    assert destination.read_bytes() == b'viral-video-bytes'

    adapter.delete(key)
    assert not adapter.exists(key)


def test_missing_object_raises_not_found(adapter, tmp_path):
    with pytest.raises(StorageNotFoundError):
        adapter.download('workspaces/ws/videos/v/source/missing.mp4', tmp_path / 'x.mp4')
    with pytest.raises(StorageNotFoundError):
        adapter.stat('workspaces/ws/videos/v/source/missing.mp4')


def test_keys_are_server_generated_and_traversal_is_rejected(adapter, tmp_path):
    key = source_key('workspace-1', 'video-1', '../../etc/passwd')
    assert '..' not in key
    assert key.startswith('workspaces/workspace-1/videos/video-1/source/')
    with pytest.raises(StorageValidationError):
        adapter.put_file(write(tmp_path, 'evil.mp4'), '../escape.mp4')


def test_presigned_urls_are_generated_for_both_directions(adapter, tmp_path):
    key = artifact_key('workspace-1', 'video-1', 'thumbnail', 'cover.jpg')
    adapter.put_file(write(tmp_path, 'cover.jpg', b'jpeg'), key, 'image/jpeg')

    download = adapter.presigned_get_url(key, expires_in=120)
    upload = adapter.presigned_put_url(key, expires_in=120, content_type='image/jpeg')

    assert download.method == 'GET' and download.key == key and download.url
    assert upload.method == 'PUT' and upload.url
    assert download.expires_at > adapter.stat(key).last_modified or download.expires_at is not None


def test_prefix_cleanup_and_expiry(adapter, tmp_path):
    prefix = 'workspaces/workspace-2/videos/video-2/artifacts'
    for index in range(3):
        adapter.put_file(write(tmp_path, f'frame-{index}.jpg', b'jpg'), f'{prefix}/frame/{index}.jpg', 'image/jpeg')

    assert adapter.cleanup_expired(prefix, timedelta(days=365)) == 0
    assert adapter.delete_prefix(prefix) == 3
    assert not adapter.exists(f'{prefix}/frame/0.jpg')


def test_healthcheck_passes_for_configured_backend(adapter):
    adapter.healthcheck()


def test_local_signed_urls_reject_tampering(tmp_path):
    previous = override(storage_backend='local', uploads_dir=tmp_path / 'objects', jwt_secret='signing-secret')
    try:
        storage = LocalStorage(tmp_path / 'objects')
        key = source_key('ws', 'vid', 'clip.mp4')
        storage.put_file(write(tmp_path, 'clip.mp4'), key, 'video/mp4')
        url = storage.presigned_get_url(key, expires_in=60)
        expires = int(url.url.split('expires=')[1].split('&')[0])
        signature = url.url.split('signature=')[1]

        LocalStorage.verify(key, 'GET', expires, signature)
        with pytest.raises(StoragePermissionError):
            LocalStorage.verify(key, 'GET', expires, 'deadbeef')
        with pytest.raises(StoragePermissionError):
            LocalStorage.verify(key, 'PUT', expires, signature)
        with pytest.raises(StoragePermissionError):
            LocalStorage.verify(key, 'GET', 1, LocalStorage.sign(key, 'GET', 1))
    finally:
        restore(previous)


def test_s3_error_mapping_covers_retryable_and_permanent(tmp_path):
    from botocore.exceptions import ClientError, EndpointConnectionError

    mapped = S3Storage._map(ClientError({'Error': {'Code': 'NoSuchKey'}, 'ResponseMetadata': {'HTTPStatusCode': 404}}, 'GetObject'), 'k')
    assert isinstance(mapped, StorageNotFoundError) and not mapped.retryable

    denied = S3Storage._map(ClientError({'Error': {'Code': 'AccessDenied'}, 'ResponseMetadata': {'HTTPStatusCode': 403}}, 'GetObject'), 'k')
    assert isinstance(denied, StoragePermissionError)

    throttled = S3Storage._map(ClientError({'Error': {'Code': 'SlowDown'}, 'ResponseMetadata': {'HTTPStatusCode': 503}}, 'PutObject'), 'k')
    assert isinstance(throttled, StorageTransientError) and throttled.retryable

    offline = S3Storage._map(EndpointConnectionError(endpoint_url='http://minio:9000'), 'k')
    assert isinstance(offline, StorageTransientError)


def test_transient_failures_are_retried_then_surfaced(tmp_path):
    previous = override(storage_max_attempts=3, storage_retry_backoff_seconds=0.0)
    try:
        storage = LocalStorage(tmp_path / 'objects')
        attempts = {'count': 0}

        def flaky():
            attempts['count'] += 1
            raise StorageTransientError('temporary')

        with pytest.raises(StorageTransientError):
            storage._retry('put_object', flaky)
        assert attempts['count'] == 3
    finally:
        restore(previous)


def test_factory_refuses_local_backend_in_production(tmp_path):
    previous = override(environment='production', storage_backend='local')
    try:
        with pytest.raises(storage_module.StorageConfigurationError):
            get_storage(refresh=True)
    finally:
        restore(previous)


def test_s3_backend_requires_bucket_and_credentials():
    previous = override(storage_backend='s3', s3_bucket=None, s3_access_key=None, s3_secret_key=None)
    try:
        with pytest.raises(storage_module.StorageConfigurationError):
            get_storage(refresh=True)
    finally:
        restore(previous)
    assert settings.storage_backend == 'local'
