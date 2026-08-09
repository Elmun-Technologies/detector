"""auth membership and billing
Revision ID: 20260810_02
Revises: 20260809_01
"""
from alembic import op
import sqlalchemy as sa
revision='20260810_02'; down_revision='20260809_01'; branch_labels=None; depends_on=None
def upgrade():
 op.create_table('workspace_members',sa.Column('id',sa.String(36),primary_key=True),sa.Column('created_at',sa.DateTime(timezone=True)),sa.Column('updated_at',sa.DateTime(timezone=True)),sa.Column('workspace_id',sa.String(36),sa.ForeignKey('workspaces.id'),nullable=False),sa.Column('user_id',sa.String(36),sa.ForeignKey('users.id'),nullable=False),sa.Column('role',sa.String(16),nullable=False),sa.UniqueConstraint('workspace_id','user_id'))
 op.create_table('roles',sa.Column('id',sa.String(36),primary_key=True),sa.Column('created_at',sa.DateTime(timezone=True)),sa.Column('updated_at',sa.DateTime(timezone=True)),sa.Column('name',sa.String(32),unique=True),sa.Column('permissions',sa.JSON))
 op.create_table('subscriptions',sa.Column('id',sa.String(36),primary_key=True),sa.Column('created_at',sa.DateTime(timezone=True)),sa.Column('updated_at',sa.DateTime(timezone=True)),sa.Column('workspace_id',sa.String(36),sa.ForeignKey('workspaces.id'),unique=True),sa.Column('plan',sa.String(20)),sa.Column('status',sa.String(20)),sa.Column('provider',sa.String(20)),sa.Column('external_id',sa.String(128)))
 op.create_table('payments',sa.Column('id',sa.String(36),primary_key=True),sa.Column('created_at',sa.DateTime(timezone=True)),sa.Column('updated_at',sa.DateTime(timezone=True)),sa.Column('workspace_id',sa.String(36),sa.ForeignKey('workspaces.id')),sa.Column('provider',sa.String(20)),sa.Column('provider_payment_id',sa.String(128),unique=True),sa.Column('amount',sa.Integer),sa.Column('currency',sa.String(8)),sa.Column('status',sa.String(20)),sa.Column('raw_event',sa.JSON))
def downgrade():
 for t in ('payments','subscriptions','roles','workspace_members'):op.drop_table(t)
