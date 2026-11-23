"""Add wallet challenges and verified links.

Revision ID: 0007
Revises: 0006
"""

from alembic import op
import sqlalchemy as sa


revision = '0007'
down_revision = '0006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "wallet_challenges",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("nonce", sa.Uuid(), nullable=False),
        sa.Column("address", sa.String(length=42), nullable=False),
        sa.Column("chain_id", sa.BigInteger(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_table(
        "wallet_links",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("address", sa.String(length=42), nullable=False),
        sa.Column("chain_id", sa.BigInteger(), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
        sa.UniqueConstraint("address", name="uq_wallet_links_address"),
    )


def downgrade() -> None:
    op.drop_table('wallet_links')
    op.drop_table('wallet_challenges')
