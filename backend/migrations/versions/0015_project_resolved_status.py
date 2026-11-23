"""Let a project end with a dispute ruling."""

from alembic import op


revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None

STATUSES = "'active', 'in_review', 'revision', 'completed', 'disputed', 'cancelled'"


def replace_check(statuses: str) -> None:
    op.drop_constraint("ck_projects_status", "projects", type_="check")
    op.create_check_constraint("ck_projects_status", "projects", f"status IN ({statuses})")


def upgrade() -> None:
    replace_check(f"{STATUSES}, 'resolved'")
    op.execute("""
        UPDATE projects SET status = 'resolved'
        WHERE EXISTS (
            SELECT 1 FROM escrow_agreements
            WHERE escrow_agreements.project_id = projects.id AND escrow_agreements.status = 'resolved'
        )
    """)
    op.execute("""
        UPDATE jobs SET status = 'closed'
        WHERE status = 'in_progress' AND EXISTS (
            SELECT 1 FROM projects WHERE projects.job_id = jobs.id AND projects.status = 'resolved'
        )
    """)
    op.execute("""
        UPDATE projects SET status = 'active'
        WHERE status = 'completed' AND EXISTS (
            SELECT 1 FROM escrow_agreements
            WHERE escrow_agreements.project_id = projects.id AND escrow_agreements.status = 'funded'
        )
    """)


def downgrade() -> None:
    op.execute("UPDATE projects SET status = 'cancelled' WHERE status = 'resolved'")
    replace_check(STATUSES)
