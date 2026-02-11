"""add assistant_reply to raw_logs

Revision ID: 20260208_assistant
Revises:
Create Date: 2026-02-08

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260208_assistant"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "raw_logs",
        sa.Column("assistant_reply", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("raw_logs", "assistant_reply")
