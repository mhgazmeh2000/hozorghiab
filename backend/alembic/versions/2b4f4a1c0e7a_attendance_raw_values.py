"""store raw ZK attendance state and punch values

Revision ID: 2b4f4a1c0e7a
Revises: 070560627f5f
"""
from alembic import op
import sqlalchemy as sa

revision = "2b4f4a1c0e7a"
down_revision = "070560627f5f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("attendance_logs", sa.Column("raw_state", sa.String(length=30), nullable=True))
    op.add_column("attendance_logs", sa.Column("raw_punch", sa.String(length=30), nullable=True))


def downgrade() -> None:
    op.drop_column("attendance_logs", "raw_punch")
    op.drop_column("attendance_logs", "raw_state")