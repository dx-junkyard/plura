"""create policies table for Policy Weaver

Revision ID: 20260222_policies
Revises: 20260213_projects
Create Date: 2026-02-22

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


revision = "20260222_policies"
down_revision = "20260213_projects"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "policies",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("dilemma_context", sa.Text, nullable=False),
        sa.Column("principle", sa.Text, nullable=False),
        sa.Column("boundary_conditions", JSONB, nullable=False, server_default="{}"),
        sa.Column(
            "enforcement_level",
            sa.String(20),
            nullable=False,
            server_default="suggest",
            index=True,
        ),
        sa.Column("ttl_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "is_strict_promoted",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "metrics",
            JSONB,
            nullable=False,
            server_default='{"override_count": 0, "applied_count": 0, "override_reasons": []}',
        ),
        sa.Column(
            "source_project_id",
            UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_by",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    # TTL切れポリシーを効率的にクエリするためのインデックス
    op.create_index(
        "ix_policies_ttl_expires_at",
        "policies",
        ["ttl_expires_at"],
    )
    op.create_index(
        "ix_policies_source_project_id",
        "policies",
        ["source_project_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_policies_source_project_id", table_name="policies")
    op.drop_index("ix_policies_ttl_expires_at", table_name="policies")
    op.drop_table("policies")
