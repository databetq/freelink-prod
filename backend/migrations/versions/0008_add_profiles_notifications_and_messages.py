"""Add profile fields, notifications and project message threads.

Revision ID: 0008
Revises: 0007
"""

from alembic import op
import sqlalchemy as sa


revision = '0008'
down_revision = '0007'
branch_labels = None
depends_on = None

EMPTY_LIST = sa.text("'[]'::json")


def upgrade() -> None:
    op.add_column("profiles", sa.Column("display_name", sa.String(length=200), nullable=True))
    op.add_column("profiles", sa.Column("title", sa.String(length=200), nullable=True))
    op.add_column("profiles", sa.Column("location", sa.String(length=200), nullable=True))
    op.add_column("profiles", sa.Column("bio", sa.Text(), nullable=True))
    op.add_column("profiles", sa.Column("avatar_color", sa.String(length=100), nullable=True))
    op.add_column("profiles", sa.Column(
        "availability", sa.String(length=16), server_default="open", nullable=False,
    ))
    op.add_column("profiles", sa.Column("hourly_rate", sa.Numeric(10, 2), nullable=True))
    for column in ("skills", "languages", "portfolio"):
        op.add_column("profiles", sa.Column(column, sa.JSON(), server_default=EMPTY_LIST, nullable=False))
    op.add_column("profiles", sa.Column("contact_name", sa.String(length=200), nullable=True))
    op.add_column("profiles", sa.Column("industry", sa.String(length=200), nullable=True))
    op.add_column("profiles", sa.Column("website", sa.String(length=300), nullable=True))
    op.create_check_constraint(
        "ck_profiles_availability", "profiles", "availability IN ('open', 'limited', 'unavailable')",
    )
    op.create_check_constraint(
        "ck_profiles_hourly_rate", "profiles", "hourly_rate IS NULL OR hourly_rate >= 0",
    )

    op.create_table(
        "notifications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("type", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("body", sa.String(length=1000), nullable=False),
        sa.Column("link", sa.String(length=255), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "type IN ('proposal', 'submission', 'message', 'payment', 'job')", name="ck_notifications_type",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])

    op.create_table(
        "message_threads",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("client_id", sa.Uuid(), nullable=False),
        sa.Column("freelancer_id", sa.Uuid(), nullable=False),
        sa.Column("client_read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("freelancer_read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["client_id"], ["profiles.id"]),
        sa.ForeignKeyConstraint(["freelancer_id"], ["profiles.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id"),
    )
    op.create_index("ix_message_threads_client_id", "message_threads", ["client_id"])
    op.create_index("ix_message_threads_freelancer_id", "message_threads", ["freelancer_id"])

    op.create_table(
        "messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("thread_id", sa.Uuid(), nullable=False),
        sa.Column("sender_id", sa.Uuid(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["thread_id"], ["message_threads.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sender_id"], ["profiles.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_messages_thread_id", "messages", ["thread_id"])

    # Projects hired before this migration get the conversation they would have had.
    op.execute(
        "INSERT INTO message_threads (id, project_id, client_id, freelancer_id, created_at) "
        "SELECT gen_random_uuid(), id, client_id, freelancer_id, created_at FROM projects"
    )


def downgrade() -> None:
    op.drop_table("messages")
    op.drop_table("message_threads")
    op.drop_table("notifications")
    op.drop_constraint("ck_profiles_hourly_rate", "profiles", type_="check")
    op.drop_constraint("ck_profiles_availability", "profiles", type_="check")
    for column in (
        "website", "industry", "contact_name", "portfolio", "languages", "skills", "hourly_rate",
        "availability", "avatar_color", "bio", "location", "title", "display_name",
    ):
        op.drop_column("profiles", column)
