"""
PLURA - Policy Model
Policy Weaver: Flash Team解散時のガバナンスルールの永続化モデル

設計思想:
  - 二段階制度化: まずは Prompt as Code（SUGGEST/WARN）として運用し、
    実績が蓄積されてから BLOCK へ昇格する
  - TTL による新陳代謝: 全ポリシーに再評価期限を設け、陳腐化を防ぐ
  - Override を主燃料とする: 逸脱理由を蓄積し、ルールの境界条件を更新する
"""
import uuid
import enum
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import String, Text, DateTime, Boolean, Integer, ForeignKey
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, utc_now


# デフォルトTTL: 30日
DEFAULT_TTL_DAYS = 30


class EnforcementLevel(str, enum.Enum):
    """ポリシーの強制力レベル"""
    SUGGEST = "suggest"  # AIの提案として表示
    WARN = "warn"        # 警告として表示（無視可能）
    BLOCK = "block"      # 強制ブロック（昇格後のみ）


class Policy(Base):
    """
    Policy Weaver で抽出されたガバナンスルール

    Flash Team のプロジェクトログから抽出された
    「現場のジレンマやトレードオフの決断」を
    再利用可能なルールとして定着させる。
    """

    __tablename__ = "policies"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # ── ルール内容 ──
    dilemma_context: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="解決したトレードオフやジレンマの背景",
    )
    principle: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="原則となるルール",
    )
    boundary_conditions: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        comment='適用条件と例外条件 {"applies_when": [...], "except_when": [...]}',
    )

    # ── 強制力・ライフサイクル ──
    enforcement_level: Mapped[str] = mapped_column(
        String(20),
        default=EnforcementLevel.SUGGEST.value,
        nullable=False,
        index=True,
        comment="強制力レベル: suggest, warn, block",
    )
    ttl_expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="このルールの再評価期限",
    )
    is_strict_promoted: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="Strict Policy（BLOCK）へ昇格済みか否か",
    )

    # ── Override メトリクス ──
    metrics: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=lambda: {
            "override_count": 0,
            "applied_count": 0,
            "override_reasons": [],
        },
        comment="override回数・適用回数などの統計情報",
    )

    # ── 出自・関連 ──
    source_project_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="SET NULL"),
        nullable=True,
        comment="抽出元プロジェクトID",
    )
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="抽出を実行したユーザーID",
    )

    # ── タイムスタンプ ──
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<Policy {self.id} enforcement={self.enforcement_level}>"
