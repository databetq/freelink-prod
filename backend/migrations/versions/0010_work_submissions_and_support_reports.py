"""Store work submissions, attachments, and support reports."""

from alembic import op
import sqlalchemy as sa


revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "work_submissions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("agreement_id", sa.Uuid(), sa.ForeignKey("escrow_agreements.id"), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("link", sa.String(2048)),
        sa.Column("status", sa.String(16), server_default="pending", nullable=False),
        sa.Column("feedback", sa.Text()),
        sa.Column("submitted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('pending', 'revision', 'approved')", name="ck_work_submissions_status"),
    )
    op.create_index("ix_work_submissions_project_id", "work_submissions", ["project_id"])
    op.create_table(
        "work_attachments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("submission_id", sa.Uuid(), sa.ForeignKey("work_submissions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
    )
    op.create_index("ix_work_attachments_submission_id", "work_attachments", ["submission_id"])
    op.create_table(
        "support_reports",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("reporter_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("projects.id")),
        sa.Column("topic", sa.String(16), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), server_default="open", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("topic IN ('general', 'payment', 'account', 'report')", name="ck_support_reports_topic"),
        sa.CheckConstraint("status IN ('open', 'resolved')", name="ck_support_reports_status"),
    )


def downgrade() -> None:
    op.drop_table("support_reports")
    op.drop_table("work_attachments")
    op.drop_table("work_submissions")
