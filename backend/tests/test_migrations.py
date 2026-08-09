"""Alembic smoke: the migration chain has to build the runtime schema.

Runs on SQLite so it is always executed; the CI integration profile runs the
same ``upgrade head`` against PostgreSQL.
"""
from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

REPO_ROOT = Path(__file__).parents[2]


def alembic_config(url: str) -> Config:
    config = Config(str(REPO_ROOT / 'alembic.ini'))
    config.set_main_option('script_location', str(REPO_ROOT / 'backend' / 'alembic'))
    config.set_main_option('sqlalchemy.url', url)
    return config


def test_upgrade_head_creates_the_media_pipeline_schema(tmp_path):
    url = f'sqlite:///{tmp_path}/pipeline.db'
    command.upgrade(alembic_config(url), 'head')
    info = inspect(create_engine(url))

    tables = set(info.get_table_names())
    assert {'videos', 'video_analyses', 'analysis_jobs', 'media_artifacts', 'provider_calls'} <= tables

    videos = {column['name'] for column in info.get_columns('videos')}
    assert {'storage_backend', 'checksum_sha256', 'video_codec', 'audio_codec', 'aspect_ratio', 'fps', 'has_audio'} <= videos

    analyses = {column['name'] for column in info.get_columns('video_analyses')}
    assert {'language', 'provider_mode', 'cost_usd', 'error_code', 'started_at', 'completed_at'} <= analyses

    jobs = {column['name'] for column in info.get_columns('analysis_jobs')}
    assert {
        'idempotency_key', 'stage', 'progress', 'max_attempts', 'error_code', 'error',
        'cancel_requested', 'heartbeat_at', 'next_retry_at', 'finished_at',
    } <= jobs

    artifacts = {column['name'] for column in info.get_columns('media_artifacts')}
    assert {'video_id', 'analysis_id', 'kind', 'storage_key', 'expires_at', 'deleted_at'} <= artifacts

    calls = {column['name'] for column in info.get_columns('provider_calls')}
    assert {'kind', 'provider', 'model', 'mode', 'status', 'attempts', 'cost_usd', 'error_code'} <= calls


def test_idempotency_key_is_unique_and_hot_columns_are_indexed(tmp_path):
    url = f'sqlite:///{tmp_path}/indexes.db'
    command.upgrade(alembic_config(url), 'head')
    info = inspect(create_engine(url))

    job_indexes = {index['name']: index for index in info.get_indexes('analysis_jobs')}
    assert bool(job_indexes['ux_analysis_jobs_idempotency_key']['unique']) is True
    assert 'ix_analysis_jobs_status' in job_indexes
    assert {index['name'] for index in info.get_indexes('media_artifacts')} >= {
        'ix_media_artifacts_video',
        'ix_media_artifacts_expires_at',
    }
    assert 'ix_provider_calls_analysis' in {index['name'] for index in info.get_indexes('provider_calls')}


def test_migration_chain_is_reversible_for_development(tmp_path):
    url = f'sqlite:///{tmp_path}/reversible.db'
    config = alembic_config(url)
    command.upgrade(config, 'head')
    command.downgrade(config, '20260810_02')
    info = inspect(create_engine(url))
    assert 'media_artifacts' not in info.get_table_names()
    command.upgrade(config, 'head')
    assert 'media_artifacts' in inspect(create_engine(url)).get_table_names()


def test_runtime_metadata_matches_the_migrated_schema(tmp_path):
    """Every table the ORM expects must exist after ``upgrade head``."""
    from app.database import Base

    url = f'sqlite:///{tmp_path}/parity.db'
    command.upgrade(alembic_config(url), 'head')
    migrated = set(inspect(create_engine(url)).get_table_names())
    expected = set(Base.metadata.tables) - {'alembic_version'}
    missing = expected - migrated
    assert not missing, f'migration chain is missing tables: {sorted(missing)}'
