"""Store a submission's commitment and its on-chain confirmation time."""

import sqlalchemy as sa
from alembic import op


revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("work_submissions", sa.Column("work_hash", sa.String(66), nullable=True))
    op.add_column("work_submissions", sa.Column("chain_submitted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("work_submissions", sa.Column("chain_review_ends_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("work_submissions", "chain_review_ends_at")
    op.drop_column("work_submissions", "chain_submitted_at")
    op.drop_column("work_submissions", "work_hash")
