"""production schema
Revision ID: 20260809_01
Revises:
Create Date: 2026-08-09
"""
from alembic import op
import sqlalchemy as sa
revision='20260809_01'; down_revision=None; branch_labels=None; depends_on=None
def table(name,*columns): op.create_table(name,*columns,sa.Column('id',sa.String(36),primary_key=True),sa.Column('created_at',sa.DateTime(timezone=True)),sa.Column('updated_at',sa.DateTime(timezone=True)))
def upgrade():
 table('users',sa.Column('telegram_id',sa.String(32),unique=True),sa.Column('phone',sa.String(32)),sa.Column('locale',sa.String(12)),sa.Column('deleted_at',sa.DateTime(timezone=True)))
 table('workspaces',sa.Column('owner_id',sa.String(36),sa.ForeignKey('users.id')),sa.Column('name',sa.String(160)),sa.Column('plan',sa.String(20)),sa.Column('industry',sa.String(120)),sa.Column('audience',sa.Text),sa.Column('objective',sa.String(80)),sa.Column('region',sa.String(80)))
 table('instagram_accounts',sa.Column('workspace_id',sa.String(36),sa.ForeignKey('workspaces.id')),sa.Column('username',sa.String(100)),sa.Column('account_type',sa.String(32)),sa.Column('offer',sa.Text),sa.Column('encrypted_token',sa.Text),sa.Column('token_key_version',sa.String(20)),sa.Column('active',sa.Boolean))
 table('videos',sa.Column('workspace_id',sa.String(36),sa.ForeignKey('workspaces.id')),sa.Column('account_id',sa.String(36),sa.ForeignKey('instagram_accounts.id')),sa.Column('storage_key',sa.String(512)),sa.Column('original_name',sa.String(255)),sa.Column('content_type',sa.String(100)),sa.Column('size_bytes',sa.Integer),sa.Column('duration_seconds',sa.Float),sa.Column('width',sa.Integer),sa.Column('height',sa.Integer),sa.Column('status',sa.String(32)))
 table('video_analyses',sa.Column('video_id',sa.String(36),sa.ForeignKey('videos.id'),unique=True),sa.Column('status',sa.String(32)),sa.Column('report',sa.JSON),sa.Column('metadata',sa.JSON),sa.Column('error',sa.Text))
 table('video_segments',sa.Column('analysis_id',sa.String(36),sa.ForeignKey('video_analyses.id')),sa.Column('start_seconds',sa.Float),sa.Column('end_seconds',sa.Float),sa.Column('kind',sa.String(40)),sa.Column('score',sa.Float),sa.Column('details',sa.JSON))
 table('content_plans',sa.Column('workspace_id',sa.String(36),sa.ForeignKey('workspaces.id')),sa.Column('month',sa.String(7)),sa.Column('title',sa.String(160)),sa.Column('status',sa.String(32)))
 table('content_items',sa.Column('plan_id',sa.String(36),sa.ForeignKey('content_plans.id')),sa.Column('scheduled_for',sa.DateTime(timezone=True)),sa.Column('topic',sa.String(255)),sa.Column('hook',sa.Text),sa.Column('script',sa.Text),sa.Column('status',sa.String(32)))
 table('competitors',sa.Column('workspace_id',sa.String(36),sa.ForeignKey('workspaces.id')),sa.Column('username',sa.String(100)),sa.Column('notes',sa.Text),sa.Column('last_analysis',sa.JSON))
 table('instagram_metrics',sa.Column('video_id',sa.String(36),sa.ForeignKey('videos.id')),sa.Column('captured_at',sa.DateTime(timezone=True)),sa.Column('views',sa.Integer),sa.Column('reach',sa.Integer),sa.Column('likes',sa.Integer),sa.Column('comments',sa.Integer),sa.Column('shares',sa.Integer),sa.Column('saves',sa.Integer))
 table('predictions',sa.Column('video_id',sa.String(36),sa.ForeignKey('videos.id')),sa.Column('predicted_views',sa.Integer),sa.Column('predicted_score',sa.Float),sa.Column('actual_views',sa.Integer),sa.Column('accuracy',sa.Float))
 table('audit_logs',sa.Column('workspace_id',sa.String(36),sa.ForeignKey('workspaces.id')),sa.Column('user_id',sa.String(36),sa.ForeignKey('users.id')),sa.Column('action',sa.String(100)),sa.Column('target_type',sa.String(60)),sa.Column('target_id',sa.String(36)),sa.Column('ip_hash',sa.String(64)),sa.Column('details',sa.JSON))
 table('analysis_jobs',sa.Column('analysis_id',sa.String(36),sa.ForeignKey('video_analyses.id')),sa.Column('task_id',sa.String(100)),sa.Column('status',sa.String(32)),sa.Column('attempts',sa.Integer),sa.Column('locked_at',sa.DateTime(timezone=True)))
def downgrade():
 for n in ['analysis_jobs','audit_logs','predictions','instagram_metrics','competitors','content_items','content_plans','video_segments','video_analyses','videos','instagram_accounts','workspaces','users']:op.drop_table(n)
