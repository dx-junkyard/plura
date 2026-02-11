"""add thread_id to raw_logs

Revision ID: 20260208_thread
Revises: 20260208_assistant
Create Date: 2026-02-08

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = "20260208_thread"
down_revision = "20260208_assistant"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "raw_logs",
        sa.Column("thread_id", UUID(as_uuid=True), nullable=True, comment="同じ会話の先頭ログの id"),
    )
    op.create_index(op.f("ix_raw_logs_thread_id"), "raw_logs", ["thread_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_raw_logs_thread_id"), table_name="raw_logs")
    op.drop_column("raw_logs", "thread_id")
