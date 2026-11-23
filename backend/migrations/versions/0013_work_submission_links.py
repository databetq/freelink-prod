"""Store multiple work links per submission."""

from alembic import op
import sqlalchemy as sa


revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("work_submissions", sa.Column("links", sa.JSON(), nullable=False, server_default="[]"))


def downgrade() -> None:
    op.drop_column("work_submissions", "links")
