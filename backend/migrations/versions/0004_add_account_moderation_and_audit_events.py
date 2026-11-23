"""Add account moderation and audit events.

Revision ID: 0004
Revises: 0003
"""

from alembic import op
import sqlalchemy as sa


revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "admin_user_status_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("previous_status", sa.String(length=16), nullable=False),
        sa.Column("new_status", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["target_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f('ix_admin_user_status_events_actor_id'), 'admin_user_status_events', ['actor_id'], unique=False)
    op.create_index(op.f('ix_admin_user_status_events_target_id'), 'admin_user_status_events', ['target_id'], unique=False)
    op.add_column('users', sa.Column('status', sa.String(length=16), server_default='active', nullable=False))
    op.create_check_constraint("ck_users_status", "users", "status IN ('active', 'suspended')")


def downgrade() -> None:
    op.drop_constraint("ck_users_status", "users", type_="check")
    op.drop_column('users', 'status')
    op.drop_index(op.f('ix_admin_user_status_events_target_id'), table_name='admin_user_status_events')
    op.drop_index(op.f('ix_admin_user_status_events_actor_id'), table_name='admin_user_status_events')
    op.drop_table('admin_user_status_events')
