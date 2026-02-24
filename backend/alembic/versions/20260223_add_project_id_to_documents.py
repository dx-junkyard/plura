"""add project_id to documents table

Revision ID: 20260223_docs_proj
Revises: 20260223_documents
Create Date: 2026-02-23

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = "20260223_docs_proj"
down_revision = "20260223_documents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column(
            "project_id",
            UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_documents_project_id",
        "documents",
        ["project_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_documents_project_id", table_name="documents")
    op.drop_column("documents", "project_id")
