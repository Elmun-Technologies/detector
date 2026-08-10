"""Private object storage.

Two adapters implement one contract:

* ``LocalStorage``  – development/test disk storage with signed, expiring URLs.
* ``S3Storage``     – production S3/MinIO with private objects, SigV4 presigned
  upload/download URLs, prefix cleanup and bucket lifecycle rules.

Rules that both adapters must honour:

* object keys are generated server side, never taken from the client;
* objects are private – no public ACL, no directory listing, no static serving;
* every failure is mapped to a typed :class:`StorageError` so the worker can
  decide between "retry later" and "fail permanently".
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import shutil
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Protocol
from collections.abc import Iterable
from urllib.parse import quote, urlencode
from uuid import uuid4

from .config import settings
from .logging_setup import get_logger

logger = get_logger('app.storage')

SAFE_NAME = re.compile(r'[^A-Za-z0-9._-]+')
SAFE_KEY = re.compile(r'^[A-Za-z0-9][A-Za-z0-9/._-]{0,511}$')


# --------------------------------------------------------------------------- errors
class StorageError(RuntimeError):
    code = 'storage_error'
    retryable = False

    def __init__(self, message: str, *, key: str | None = None, code: str | None = None):
        super().__init__(message)
        self.key = key
        if code:
            self.code = code


class StorageConfigurationError(StorageError):
    code = 'storage_configuration_error'


class StorageValidationError(StorageError):
    code = 'storage_validation_error'


class StorageNotFoundError(StorageError):
    code = 'storage_not_found'


class StoragePermissionError(StorageError):
    code = 'storage_permission_denied'


class StorageTransientError(StorageError):
    code = 'storage_unavailable'
    retryable = True


# --------------------------------------------------------------------------- value objects
@dataclass(frozen=True)
class StoredObject:
    key: str
    size_bytes: int
    content_type: str | None
    backend: str
    checksum_sha256: str | None = None


@dataclass(frozen=True)
class ObjectStat:
    key: str
    size_bytes: int
    content_type: str | None
    last_modified: datetime | None


@dataclass(frozen=True)
class PresignedUrl:
    url: str
    method: str
    key: str
    expires_at: datetime
    headers: dict[str, str]


# --------------------------------------------------------------------------- key helpers
def safe_filename(name: str) -> str:
    cleaned = SAFE_NAME.sub('-', Path(name).name).strip('.-')
    return cleaned[:120] or 'video.mp4'


def source_key(workspace_id: str, video_id: str, filename: str) -> str:
    return f'workspaces/{workspace_id}/videos/{video_id}/source/{uuid4().hex}-{safe_filename(filename)}'


def artifact_key(workspace_id: str, video_id: str, kind: str, filename: str) -> str:
    kind = SAFE_NAME.sub('-', kind) or 'artifact'
    return f'workspaces/{workspace_id}/videos/{video_id}/artifacts/{kind}/{uuid4().hex}-{safe_filename(filename)}'


def validate_key(key: str) -> str:
    if not key or '..' in key or key.startswith('/') or not SAFE_KEY.match(key):
        raise StorageValidationError(f'Rejected object key: {key!r}', key=key)
    return key


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def signing_key() -> bytes:
    secret = settings.jwt_secret or settings.encryption_key
    if not secret:
        raise StorageConfigurationError('JWT_SECRET or ENCRYPTION_KEY is required to sign storage URLs')
    return secret.encode()


# --------------------------------------------------------------------------- contract
class ObjectStorage(Protocol):
    backend: str

    def put_file(self, source: Path, key: str, content_type: str | None = None) -> StoredObject: ...
    def put_bytes(self, data: bytes, key: str, content_type: str | None = None) -> StoredObject: ...
    def download(self, key: str, destination: Path) -> Path: ...
    def delete(self, key: str) -> None: ...
    def delete_prefix(self, prefix: str) -> int: ...
    def exists(self, key: str) -> bool: ...
    def stat(self, key: str) -> ObjectStat: ...
    def presigned_get_url(self, key: str, expires_in: int | None = None) -> PresignedUrl: ...
    def presigned_put_url(self, key: str, expires_in: int | None = None, content_type: str | None = None) -> PresignedUrl: ...
    def cleanup_expired(self, prefix: str, older_than: timedelta) -> int: ...
    def healthcheck(self) -> None: ...


class BaseStorage:
    backend = 'base'

    def _retry(self, operation: str, call):
        """Retry transient storage failures with exponential backoff."""
        attempts = max(1, settings.storage_max_attempts)
        delay = settings.storage_retry_backoff_seconds
        last: StorageError | None = None
        for attempt in range(1, attempts + 1):
            try:
                return call()
            except StorageTransientError as error:
                last = error
                logger.warning(
                    'storage operation retry',
                    extra={'operation': operation, 'attempt': attempt, 'error_code': error.code},
                )
                if attempt == attempts:
                    break
                time.sleep(delay)
                delay = min(delay * 2, 8.0)
        raise last if last else StorageError(f'{operation} failed')

    # convenience shared by both adapters
    def put_bytes(self, data: bytes, key: str, content_type: str | None = None) -> StoredObject:
        import tempfile

        with tempfile.NamedTemporaryFile(delete=False) as handle:
            handle.write(data)
            temporary = Path(handle.name)
        try:
            return self.put_file(temporary, key, content_type)
        finally:
            temporary.unlink(missing_ok=True)


# --------------------------------------------------------------------------- local adapter
class LocalStorage(BaseStorage):
    """Private on-disk storage for local development and tests.

    Files are stored with owner-only permissions and are never served by a
    static file handler; downloads go through the signed URL endpoint.
    """

    backend = 'local'

    def __init__(self, root: Path | None = None):
        self.root = Path(root or settings.uploads_dir)

    def _path(self, key: str) -> Path:
        validate_key(key)
        target = (self.root / key).resolve()
        root = self.root.resolve()
        if not str(target).startswith(str(root)):
            raise StorageValidationError('Object key escapes the storage root', key=key)
        return target

    def put_file(self, source: Path, key: str, content_type: str | None = None) -> StoredObject:
        target = self._path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            checksum = sha256_file(source)
            size = source.stat().st_size
            shutil.move(str(source), str(target))
            os.chmod(target, 0o600)
        except FileNotFoundError as error:
            raise StorageNotFoundError(f'Source file missing: {source}', key=key) from error
        except PermissionError as error:
            raise StoragePermissionError(str(error), key=key) from error
        except OSError as error:
            raise StorageTransientError(f'Local write failed: {error}', key=key) from error
        return StoredObject(key=key, size_bytes=size, content_type=content_type, backend=self.backend, checksum_sha256=checksum)

    def download(self, key: str, destination: Path) -> Path:
        source = self._path(key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copyfile(source, destination)
        except FileNotFoundError as error:
            raise StorageNotFoundError(f'Object not found: {key}', key=key) from error
        except PermissionError as error:
            raise StoragePermissionError(str(error), key=key) from error
        except OSError as error:
            raise StorageTransientError(f'Local read failed: {error}', key=key) from error
        return destination

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def delete_prefix(self, prefix: str) -> int:
        base = (self.root / prefix).resolve()
        if not str(base).startswith(str(self.root.resolve())) or not base.exists():
            return 0
        removed = sum(1 for path in base.rglob('*') if path.is_file())
        shutil.rmtree(base, ignore_errors=True)
        return removed

    def exists(self, key: str) -> bool:
        return self._path(key).exists()

    def stat(self, key: str) -> ObjectStat:
        path = self._path(key)
        if not path.exists():
            raise StorageNotFoundError(f'Object not found: {key}', key=key)
        info = path.stat()
        return ObjectStat(
            key=key,
            size_bytes=info.st_size,
            content_type=None,
            last_modified=datetime.fromtimestamp(info.st_mtime, tz=timezone.utc),
        )

    # -- signed URLs ------------------------------------------------------
    @staticmethod
    def sign(key: str, method: str, expires: int) -> str:
        payload = f'{method.upper()}:{key}:{expires}'.encode()
        return hmac.new(signing_key(), payload, hashlib.sha256).hexdigest()

    @classmethod
    def verify(cls, key: str, method: str, expires: int, signature: str) -> None:
        if expires < int(time.time()):
            raise StoragePermissionError('Signed storage URL has expired', key=key)
        if not hmac.compare_digest(cls.sign(key, method, expires), signature or ''):
            raise StoragePermissionError('Invalid storage URL signature', key=key)

    def _presign(self, key: str, method: str, expires_in: int | None, content_type: str | None) -> PresignedUrl:
        validate_key(key)
        ttl = expires_in or settings.storage_url_ttl_seconds
        expires = int(time.time()) + ttl
        query = urlencode({'expires': expires, 'signature': self.sign(key, method, expires)})
        headers = {'Content-Type': content_type} if content_type and method == 'PUT' else {}
        return PresignedUrl(
            url=f'/v1/storage/objects/{quote(key)}?{query}',
            method=method,
            key=key,
            expires_at=datetime.fromtimestamp(expires, tz=timezone.utc),
            headers=headers,
        )

    def presigned_get_url(self, key: str, expires_in: int | None = None) -> PresignedUrl:
        return self._presign(key, 'GET', expires_in, None)

    def presigned_put_url(self, key: str, expires_in: int | None = None, content_type: str | None = None) -> PresignedUrl:
        return self._presign(key, 'PUT', expires_in, content_type)

    def cleanup_expired(self, prefix: str, older_than: timedelta) -> int:
        base = (self.root / prefix)
        if not base.exists():
            return 0
        cutoff = time.time() - older_than.total_seconds()
        removed = 0
        for path in base.rglob('*'):
            if path.is_file() and path.stat().st_mtime < cutoff:
                path.unlink(missing_ok=True)
                removed += 1
        return removed

    def healthcheck(self) -> None:
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            probe = self.root / '.healthcheck'
            probe.write_text('ok', encoding='utf-8')
            probe.unlink(missing_ok=True)
        except OSError as error:
            raise StorageTransientError(f'Local storage is not writable: {error}') from error


# --------------------------------------------------------------------------- s3 adapter
class S3Storage(BaseStorage):
    """Production S3/MinIO adapter (private objects, SigV4 presigned URLs)."""

    backend = 's3'

    def __init__(self):
        if not settings.s3_bucket:
            raise StorageConfigurationError('S3_BUCKET is required when STORAGE_BACKEND=s3')
        if not (settings.s3_access_key and settings.s3_secret_key):
            raise StorageConfigurationError('S3_ACCESS_KEY and S3_SECRET_KEY are required when STORAGE_BACKEND=s3')
        try:
            import boto3
            from botocore.config import Config
        except ImportError as error:  # pragma: no cover - dependency is declared
            raise StorageConfigurationError('boto3 is required for the S3 storage backend') from error

        self.bucket = settings.s3_bucket
        self.client = boto3.client(
            's3',
            endpoint_url=settings.s3_endpoint or None,
            region_name=settings.s3_region,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            config=Config(
                signature_version='s3v4',
                retries={'max_attempts': max(1, settings.storage_max_attempts), 'mode': 'standard'},
                s3={'addressing_style': 'path' if settings.s3_force_path_style else 'auto'},
            ),
        )

    # -- error mapping ----------------------------------------------------
    @staticmethod
    def _map(error: Exception, key: str | None = None) -> StorageError:
        from botocore.exceptions import BotoCoreError, ClientError

        if isinstance(error, ClientError):
            response = error.response or {}
            code = str(response.get('Error', {}).get('Code', ''))
            status = int(response.get('ResponseMetadata', {}).get('HTTPStatusCode', 0) or 0)
            if code in {'NoSuchKey', 'NoSuchBucket', '404'} or status == 404:
                return StorageNotFoundError(f'Object not found: {key}', key=key)
            if code in {'AccessDenied', 'InvalidAccessKeyId', 'SignatureDoesNotMatch', '403'} or status == 403:
                return StoragePermissionError(f'Storage access denied: {code}', key=key)
            if status >= 500 or code in {'SlowDown', 'RequestTimeout', 'ServiceUnavailable', 'InternalError'}:
                return StorageTransientError(f'Storage temporarily unavailable: {code}', key=key)
            return StorageError(f'Storage error {code}', key=key)
        if isinstance(error, BotoCoreError):
            return StorageTransientError(f'Storage connection failure: {type(error).__name__}', key=key)
        return StorageError(str(error), key=key)

    def _call(self, operation: str, func, key: str | None = None):
        def run():
            try:
                return func()
            except Exception as error:
                raise self._map(error, key) from error

        return self._retry(operation, run)

    # -- operations -------------------------------------------------------
    def _extra_args(self, content_type: str | None) -> dict:
        extra: dict[str, str] = {'ACL': 'private'}
        if content_type:
            extra['ContentType'] = content_type
        if settings.s3_server_side_encryption:
            extra['ServerSideEncryption'] = settings.s3_server_side_encryption
        return extra

    def put_file(self, source: Path, key: str, content_type: str | None = None) -> StoredObject:
        validate_key(key)
        if not source.exists():
            raise StorageNotFoundError(f'Source file missing: {source}', key=key)
        checksum = sha256_file(source)
        size = source.stat().st_size
        self._call('put_object', lambda: self.client.upload_file(str(source), self.bucket, key, ExtraArgs=self._extra_args(content_type)), key)
        source.unlink(missing_ok=True)
        return StoredObject(key=key, size_bytes=size, content_type=content_type, backend=self.backend, checksum_sha256=checksum)

    def download(self, key: str, destination: Path) -> Path:
        validate_key(key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        self._call('get_object', lambda: self.client.download_file(self.bucket, key, str(destination)), key)
        return destination

    def delete(self, key: str) -> None:
        validate_key(key)
        self._call('delete_object', lambda: self.client.delete_object(Bucket=self.bucket, Key=key), key)

    def _iter_keys(self, prefix: str) -> Iterable[dict]:
        paginator = self.client.get_paginator('list_objects_v2')
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            yield from page.get('Contents', [])

    def delete_prefix(self, prefix: str) -> int:
        def run() -> int:
            removed = 0
            batch: list[dict] = []
            for item in self._iter_keys(prefix):
                batch.append({'Key': item['Key']})
                if len(batch) == 1000:
                    self.client.delete_objects(Bucket=self.bucket, Delete={'Objects': batch})
                    removed += len(batch)
                    batch = []
            if batch:
                self.client.delete_objects(Bucket=self.bucket, Delete={'Objects': batch})
                removed += len(batch)
            return removed

        return self._call('delete_prefix', run, prefix)

    def exists(self, key: str) -> bool:
        try:
            self.stat(key)
            return True
        except StorageNotFoundError:
            return False

    def stat(self, key: str) -> ObjectStat:
        validate_key(key)
        head = self._call('head_object', lambda: self.client.head_object(Bucket=self.bucket, Key=key), key)
        return ObjectStat(
            key=key,
            size_bytes=int(head.get('ContentLength', 0)),
            content_type=head.get('ContentType'),
            last_modified=head.get('LastModified'),
        )

    def presigned_get_url(self, key: str, expires_in: int | None = None) -> PresignedUrl:
        validate_key(key)
        ttl = expires_in or settings.storage_url_ttl_seconds
        url = self._call(
            'presign_get',
            lambda: self.client.generate_presigned_url('get_object', Params={'Bucket': self.bucket, 'Key': key}, ExpiresIn=ttl),
            key,
        )
        return PresignedUrl(url=url, method='GET', key=key, expires_at=datetime.now(timezone.utc) + timedelta(seconds=ttl), headers={})

    def presigned_put_url(self, key: str, expires_in: int | None = None, content_type: str | None = None) -> PresignedUrl:
        validate_key(key)
        ttl = expires_in or settings.storage_url_ttl_seconds
        params = {'Bucket': self.bucket, 'Key': key, 'ACL': 'private'}
        if content_type:
            params['ContentType'] = content_type
        if settings.s3_server_side_encryption:
            params['ServerSideEncryption'] = settings.s3_server_side_encryption
        url = self._call('presign_put', lambda: self.client.generate_presigned_url('put_object', Params=params, ExpiresIn=ttl), key)
        headers = {'x-amz-acl': 'private'}
        if content_type:
            headers['Content-Type'] = content_type
        return PresignedUrl(url=url, method='PUT', key=key, expires_at=datetime.now(timezone.utc) + timedelta(seconds=ttl), headers=headers)

    def cleanup_expired(self, prefix: str, older_than: timedelta) -> int:
        cutoff = datetime.now(timezone.utc) - older_than

        def run() -> int:
            stale = [{'Key': item['Key']} for item in self._iter_keys(prefix) if item['LastModified'] < cutoff]
            for index in range(0, len(stale), 1000):
                self.client.delete_objects(Bucket=self.bucket, Delete={'Objects': stale[index:index + 1000]})
            return len(stale)

        return self._call('cleanup_expired', run, prefix)

    def ensure_bucket(self) -> None:
        """Create the bucket when the endpoint allows it (MinIO bootstrap)."""
        try:
            self.client.head_bucket(Bucket=self.bucket)
        except Exception:
            self._call('create_bucket', lambda: self.client.create_bucket(Bucket=self.bucket))

    def ensure_lifecycle(self) -> None:
        """Expire temporary artifacts and aged source media server side."""
        artifact_days = max(1, round(settings.artifact_retention_hours / 24) or 1)
        rules = [
            {
                'ID': 'viral-temp-artifacts',
                'Filter': {'Prefix': 'tmp/'},
                'Status': 'Enabled',
                'Expiration': {'Days': 1},
                'AbortIncompleteMultipartUpload': {'DaysAfterInitiation': 1},
            },
            {
                'ID': 'viral-analysis-artifacts',
                'Filter': {'Prefix': 'workspaces/'},
                'Status': 'Enabled',
                'NoncurrentVersionExpiration': {'NoncurrentDays': artifact_days},
                'AbortIncompleteMultipartUpload': {'DaysAfterInitiation': 1},
            },
        ]
        self._call(
            'put_bucket_lifecycle_configuration',
            lambda: self.client.put_bucket_lifecycle_configuration(Bucket=self.bucket, LifecycleConfiguration={'Rules': rules}),
        )

    def healthcheck(self) -> None:
        self._call('head_bucket', lambda: self.client.head_bucket(Bucket=self.bucket))


# --------------------------------------------------------------------------- factory
_cache: dict[tuple, ObjectStorage] = {}


def _cache_key() -> tuple:
    return (
        settings.storage_backend,
        str(settings.uploads_dir),
        settings.s3_bucket,
        settings.s3_endpoint,
        settings.s3_access_key,
    )


def get_storage(refresh: bool = False) -> ObjectStorage:
    key = _cache_key()
    if refresh or key not in _cache:
        backend = settings.storage_backend
        if backend == 's3':
            _cache[key] = S3Storage()
        elif backend == 'local':
            if settings.is_production:
                raise StorageConfigurationError('STORAGE_BACKEND=local is not allowed in production')
            _cache[key] = LocalStorage()
        else:
            raise StorageConfigurationError(f'Unknown STORAGE_BACKEND: {backend}')
    return _cache[key]


def reset_storage_cache() -> None:
    _cache.clear()
