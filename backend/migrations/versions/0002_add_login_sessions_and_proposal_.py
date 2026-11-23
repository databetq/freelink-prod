"""Add login sessions and proposal attachments.

Revision ID: 0002
Revises: 0001
"""

from alembic import op
import sqlalchemy as sa


revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'login_sessions',
        sa.Column('token_hash', sa.String(length=64), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('token_hash'),
    )
    op.create_index(op.f('ix_login_sessions_expires_at'), 'login_sessions', ['expires_at'], unique=False)
    op.create_index(op.f('ix_login_sessions_user_id'), 'login_sessions', ['user_id'], unique=False)
    op.add_column('proposals', sa.Column('attachments', sa.JSON(), server_default='[]', nullable=False))


def downgrade() -> None:
    op.drop_column('proposals', 'attachments')
    op.drop_index(op.f('ix_login_sessions_user_id'), table_name='login_sessions')
    op.drop_index(op.f('ix_login_sessions_expires_at'), table_name='login_sessions')
    op.drop_table('login_sessions')
