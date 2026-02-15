"""add deep_research to logintent enum

Revision ID: 20260212_deep_research
Revises: 20260208_thread
Create Date: 2026-02-12

"""
from alembic import op


revision = "20260212_deep_research"
down_revision = "20260211_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # PostgreSQL の ENUM 型に新しい値を追加
    op.execute("ALTER TYPE logintent ADD VALUE IF NOT EXISTS 'deep_research'")


def downgrade() -> None:
    # PostgreSQL では ENUM 値の削除が直接サポートされていないため、
    # 型の再作成が必要。既存データに deep_research が含まれる場合は
    # まず log に変換してから型を再作成する。
    op.execute(
        "UPDATE raw_logs SET intent = 'log' WHERE intent = 'deep_research'"
    )
    op.execute("ALTER TABLE raw_logs ALTER COLUMN intent TYPE VARCHAR(50)")
    op.execute("DROP TYPE IF EXISTS logintent")
    op.execute("CREATE TYPE logintent AS ENUM ('log', 'vent', 'structure', 'state')")
    op.execute(
        "ALTER TABLE raw_logs ALTER COLUMN intent TYPE logintent "
        "USING intent::logintent"
    )
