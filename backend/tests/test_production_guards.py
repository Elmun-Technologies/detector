"""Production guard rails.

Production must refuse to start on a development configuration, and every
"convenient" development affordance (inline queue, local disk storage, demo
narrative, legacy endpoints) must be unavailable there.
"""
from __future__ import annotations

import pytest

from app.config import Settings, settings
from app.storage import StorageConfigurationError, get_storage
from conftest import override, restore


def production(**overrides):
    """Settings-style override into production mode."""
    values = {'environment': 'production'}
    values.update(overrides)
    return override(**values)


def test_development_configuration_is_rejected_in_production():
    previous = production(
        database_url='sqlite:///./data/viral.db',
        queue_mode='inline',
        storage_backend='local',
        jwt_secret='development-only-change-me',
        encryption_key=None,
        s3_bucket=None,
        s3_access_key=None,
        s3_secret_key=None,
        openai_api_key=None,
        allow_demo_providers=True,
    )
    try:
        missing = settings.missing_production_settings()
        assert 'DATABASE_URL must be PostgreSQL' in missing
        assert 'QUEUE_MODE=celery' in missing
        assert 'STORAGE_BACKEND=s3' in missing
        assert 'JWT_SECRET' in missing
        assert 'ENCRYPTION_KEY' in missing
        assert 'S3_BUCKET' in missing
        assert 'ALLOW_DEMO_PROVIDERS must be false' in missing
        with pytest.raises(RuntimeError) as error:
            settings.validate_production()
        assert 'Production configuration error' in str(error.value)
    finally:
        restore(previous)


def test_a_complete_production_configuration_passes_validation():
    previous = production(
        database_url='postgresql+psycopg://viral:viral@db:5432/viral',
        queue_mode='celery',
        redis_url='redis://redis:6379/0',
        storage_backend='s3',
        s3_bucket='viral-media',
        s3_access_key='key',
        s3_secret_key='secret',
        jwt_secret='a-real-secret',
        encryption_key='a-real-fernet-key',
        openai_api_key='sk-real',
        allow_demo_providers=False,
    )
    try:
        assert settings.missing_production_settings() == []
        settings.validate_production()  # must not raise
        assert settings.eager_queue is False
        assert settings.demo_providers_enabled is False
    finally:
        restore(previous)


def test_inline_queue_is_ignored_and_refused_in_production():
    previous = production(queue_mode='inline')
    try:
        assert settings.eager_queue is False, 'production never runs tasks inline'
        from app.celery_app import build_celery

        with pytest.raises(RuntimeError) as error:
            build_celery()
        assert 'inline execution' in str(error.value)
    finally:
        restore(previous)


def test_local_storage_backend_is_refused_in_production():
    previous = production(storage_backend='local')
    try:
        with pytest.raises(StorageConfigurationError):
            get_storage()
    finally:
        restore(previous)


def test_demo_providers_are_disabled_in_production():
    previous = production(allow_demo_providers=True)
    try:
        assert settings.demo_providers_enabled is False
    finally:
        restore(previous)


def test_legacy_development_endpoints_are_gone_in_production():
    from fastapi import HTTPException

    from app.legacy import development_legacy_only

    previous = production()
    try:
        with pytest.raises(HTTPException) as error:
            development_legacy_only()
        assert error.value.status_code == 410
    finally:
        restore(previous)


def test_settings_defaults_are_development_safe():
    """A freshly constructed Settings object must not claim to be production."""
    fresh = Settings()
    assert fresh.is_production is False
    assert fresh.storage_backend in {'local', 's3'}
    assert fresh.log_format in {'json', 'text'}
