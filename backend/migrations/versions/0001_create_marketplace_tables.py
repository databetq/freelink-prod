""" Create marketplace tables

Revision ID: 0001
Revises: 
"""

from alembic import op
import sqlalchemy as sa


revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'users',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('google_subject', sa.String(length=255), nullable=False),
        sa.Column('email', sa.String(length=320), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('role', sa.String(length=16), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("role IN ('client', 'freelancer', 'admin')", name='ck_users_role'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('google_subject'),
    )
    op.create_table(
        'profiles',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id'),
    )
    op.create_table(
        'jobs',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('client_id', sa.Uuid(), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('category', sa.String(length=100), nullable=False),
        sa.Column('skills', sa.JSON(), nullable=False),
        sa.Column('deliverables', sa.JSON(), nullable=False),
        sa.Column('budget_min', sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column('budget_max', sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column('budget_type', sa.String(length=16), nullable=False),
        sa.Column('duration', sa.String(length=100), nullable=False),
        sa.Column('experience', sa.String(length=100), nullable=False),
        sa.Column('deadline', sa.Date(), nullable=True),
        sa.Column('status', sa.String(length=16), server_default='open', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("budget_type IN ('fixed', 'hourly')", name='ck_jobs_budget_type'),
        sa.CheckConstraint("status IN ('open', 'draft', 'in_progress', 'closed')", name='ck_jobs_status'),
        sa.CheckConstraint('budget_min >= 0 AND budget_max >= budget_min', name='ck_jobs_budget'),
        sa.ForeignKeyConstraint(['client_id'], ['profiles.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_jobs_client_id'), 'jobs', ['client_id'], unique=False)
    op.create_table(
        'proposals',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('job_id', sa.Uuid(), nullable=False),
        sa.Column('freelancer_id', sa.Uuid(), nullable=False),
        sa.Column('bid_amount', sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column('delivery_days', sa.Integer(), nullable=False),
        sa.Column('cover_letter', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=16), server_default='pending', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("status IN ('pending', 'shortlisted', 'hired', 'rejected', 'withdrawn')", name='ck_proposals_status'),
        sa.CheckConstraint('bid_amount > 0 AND delivery_days > 0', name='ck_proposals_offer'),
        sa.ForeignKeyConstraint(['freelancer_id'], ['profiles.id']),
        sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('job_id', 'freelancer_id', name='uq_proposals_job_freelancer'),
    )
    op.create_index(op.f('ix_proposals_freelancer_id'), 'proposals', ['freelancer_id'], unique=False)
    op.create_table(
        'projects',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('job_id', sa.Uuid(), nullable=False),
        sa.Column('proposal_id', sa.Uuid(), nullable=False),
        sa.Column('client_id', sa.Uuid(), nullable=False),
        sa.Column('freelancer_id', sa.Uuid(), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('budget', sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column('due_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('status', sa.String(length=16), server_default='active', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("status IN ('active', 'in_review', 'revision', 'completed', 'disputed', 'cancelled')", name='ck_projects_status'),
        sa.CheckConstraint('budget > 0', name='ck_projects_budget'),
        sa.CheckConstraint('client_id <> freelancer_id', name='ck_projects_distinct_parties'),
        sa.ForeignKeyConstraint(['client_id'], ['profiles.id']),
        sa.ForeignKeyConstraint(['freelancer_id'], ['profiles.id']),
        sa.ForeignKeyConstraint(['job_id'], ['jobs.id']),
        sa.ForeignKeyConstraint(['proposal_id'], ['proposals.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('job_id'),
        sa.UniqueConstraint('proposal_id'),
    )
    op.create_index(op.f('ix_projects_client_id'), 'projects', ['client_id'], unique=False)
    op.create_index(op.f('ix_projects_freelancer_id'), 'projects', ['freelancer_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_projects_freelancer_id'), table_name='projects')
    op.drop_index(op.f('ix_projects_client_id'), table_name='projects')
    op.drop_table('projects')
    op.drop_index(op.f('ix_proposals_freelancer_id'), table_name='proposals')
    op.drop_table('proposals')
    op.drop_index(op.f('ix_jobs_client_id'), table_name='jobs')
    op.drop_table('jobs')
    op.drop_table('profiles')
    op.drop_table('users')
