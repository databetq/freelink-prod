"""Store support conversations and track ticket activity."""

from alembic import op
import sqlalchemy as sa


revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("support_reports", sa.Column("updated_at", sa.DateTime(timezone=True)))
    op.execute("UPDATE support_reports SET updated_at = created_at")
    op.alter_column("support_reports", "updated_at", server_default=sa.func.now(), nullable=False)
    op.create_index("ix_support_reports_reporter_id", "support_reports", ["reporter_id"])
    op.drop_constraint("ck_support_reports_status", "support_reports", type_="check")
    op.create_check_constraint("ck_support_reports_status", "support_reports", "status IN ('open', 'waiting', 'resolved')")
    op.create_table(
        "support_report_messages",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("report_id", sa.Uuid(), sa.ForeignKey("support_reports.id", ondelete="CASCADE"), nullable=False),
        sa.Column("author_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("from_admin", sa.Boolean(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_support_report_messages_report_id", "support_report_messages", ["report_id"])
    op.drop_constraint("ck_notifications_type", "notifications", type_="check")
    op.create_check_constraint("ck_notifications_type", "notifications",
                               "type IN ('proposal', 'submission', 'message', 'payment', 'job', 'support')")


def downgrade() -> None:
    op.execute("UPDATE notifications SET type = 'message' WHERE type = 'support'")
    op.drop_constraint("ck_notifications_type", "notifications", type_="check")
    op.create_check_constraint("ck_notifications_type", "notifications",
                               "type IN ('proposal', 'submission', 'message', 'payment', 'job')")
    op.drop_table("support_report_messages")
    op.execute("UPDATE support_reports SET status = 'open' WHERE status = 'waiting'")
    op.drop_constraint("ck_support_reports_status", "support_reports", type_="check")
    op.create_check_constraint("ck_support_reports_status", "support_reports", "status IN ('open', 'resolved')")
    op.drop_index("ix_support_reports_reporter_id", table_name="support_reports")
    op.drop_column("support_reports", "updated_at")
