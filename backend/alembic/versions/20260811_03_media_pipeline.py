"""media pipeline artifacts, provider cost ledger and job control columns

Revision ID: 20260811_03
Revises: 20260810_02
Create Date: 2026-08-11

Additive only: new tables plus nullable/defaulted columns, so the migration is
safe to run against a live production database before the new worker rolls out.
"""
from alembic import op
import sqlalchemy as sa

revision = '20260811_03'
down_revision = '20260810_02'
branch_labels = None
depends_on = None

VIDEO_COLUMN_NAMES = ('storage_backend', 'checksum_sha256', 'video_codec', 'audio_codec', 'aspect_ratio', 'fps', 'has_audio')
ANALYSIS_COLUMN_NAMES = ('language', 'provider_mode', 'cost_usd', 'error_code', 'started_at', 'completed_at')
JOB_COLUMN_NAMES = (
    'idempotency_key', 'stage', 'progress', 'max_attempts', 'error_code', 'error',
    'cancel_requested', 'heartbeat_at', 'next_retry_at', 'finished_at',
)


def video_columns() -> list[sa.Column]:
    return [
        sa.Column('storage_backend', sa.String(16)),
        sa.Column('checksum_sha256', sa.String(64)),
        sa.Column('video_codec', sa.String(32)),
        sa.Column('audio_codec', sa.String(32)),
        sa.Column('aspect_ratio', sa.String(16)),
        sa.Column('fps', sa.Float()),
        sa.Column('has_audio', sa.Boolean()),
    ]


def analysis_columns() -> list[sa.Column]:
    return [
        sa.Column('language', sa.String(12)),
        sa.Column('provider_mode', sa.String(16)),
        sa.Column('cost_usd', sa.Float()),
        sa.Column('error_code', sa.String(64)),
        sa.Column('started_at', sa.DateTime(timezone=True)),
        sa.Column('completed_at', sa.DateTime(timezone=True)),
    ]


def job_columns() -> list[sa.Column]:
    return [
        sa.Column('idempotency_key', sa.String(128)),
        sa.Column('stage', sa.String(32)),
        sa.Column('progress', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('max_attempts', sa.Integer(), nullable=False, server_default='3'),
        sa.Column('error_code', sa.String(64)),
        sa.Column('error', sa.Text()),
        sa.Column('cancel_requested', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('heartbeat_at', sa.DateTime(timezone=True)),
        sa.Column('next_retry_at', sa.DateTime(timezone=True)),
        sa.Column('finished_at', sa.DateTime(timezone=True)),
    ]


def upgrade():
    for column in video_columns():
        op.add_column('videos', column)
    for column in analysis_columns():
        op.add_column('video_analyses', column)
    for column in job_columns():
        op.add_column('analysis_jobs', column)
    # SQLite cannot add a UNIQUE column, so the constraint is a unique index.
    op.create_index('ux_analysis_jobs_idempotency_key', 'analysis_jobs', ['idempotency_key'], unique=True)
    op.create_index('ix_analysis_jobs_status', 'analysis_jobs', ['status'])

    op.create_table(
        'media_artifacts',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True)),
        sa.Column('updated_at', sa.DateTime(timezone=True)),
        sa.Column('video_id', sa.String(36), sa.ForeignKey('videos.id'), nullable=False),
        sa.Column('analysis_id', sa.String(36), sa.ForeignKey('video_analyses.id')),
        sa.Column('kind', sa.String(32), nullable=False),
        sa.Column('storage_key', sa.String(512), nullable=False),
        sa.Column('content_type', sa.String(80)),
        sa.Column('size_bytes', sa.Integer()),
        sa.Column('timestamp_seconds', sa.Float()),
        sa.Column('metadata', sa.JSON()),
        sa.Column('expires_at', sa.DateTime(timezone=True)),
        sa.Column('deleted_at', sa.DateTime(timezone=True)),
    )
    op.create_index('ix_media_artifacts_video', 'media_artifacts', ['video_id', 'kind'])
    op.create_index('ix_media_artifacts_expires_at', 'media_artifacts', ['expires_at'])

    op.create_table(
        'provider_calls',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True)),
        sa.Column('updated_at', sa.DateTime(timezone=True)),
        sa.Column('analysis_id', sa.String(36), sa.ForeignKey('video_analyses.id'), nullable=False),
        sa.Column('kind', sa.String(24), nullable=False),
        sa.Column('provider', sa.String(48), nullable=False),
        sa.Column('model', sa.String(64)),
        sa.Column('mode', sa.String(16), nullable=False, server_default='production'),
        sa.Column('status', sa.String(16), nullable=False, server_default='ok'),
        sa.Column('attempts', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('duration_ms', sa.Integer()),
        sa.Column('input_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('output_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('cost_usd', sa.Float(), nullable=False, server_default='0'),
        sa.Column('error_code', sa.String(64)),
    )
    op.create_index('ix_provider_calls_analysis', 'provider_calls', ['analysis_id'])


def downgrade():
    op.drop_index('ix_provider_calls_analysis', table_name='provider_calls')
    op.drop_table('provider_calls')
    op.drop_index('ix_media_artifacts_expires_at', table_name='media_artifacts')
    op.drop_index('ix_media_artifacts_video', table_name='media_artifacts')
    op.drop_table('media_artifacts')
    op.drop_index('ix_analysis_jobs_status', table_name='analysis_jobs')
    op.drop_index('ux_analysis_jobs_idempotency_key', table_name='analysis_jobs')
    for name in reversed(JOB_COLUMN_NAMES):
        op.drop_column('analysis_jobs', name)
    for name in reversed(ANALYSIS_COLUMN_NAMES):
        op.drop_column('video_analyses', name)
    for name in reversed(VIDEO_COLUMN_NAMES):
        op.drop_column('videos', name)
