"""
PLURA - Insight Card Model
Layer 3: Public Plaza のインサイトモデル
精製・匿名化された知見を保存する
"""
import uuid
from datetime import datetime
from enum import Enum
from typing import Optional, List, TYPE_CHECKING

from sqlalchemy import (
    String,
    Text,
    DateTime,
    ForeignKey,
    Enum as SQLEnum,
    Integer,
    Float,
)
from sqlalchemy.dialects.postgresql import UUID, ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, utc_now

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.raw_log import RawLog


class InsightStatus(str, Enum):
    """インサイトの状態"""

    DRAFT = "draft"  # 通常（スコア80未満、保存のみ）
    PENDING_APPROVAL = "pending_approval"  # 推奨（スコア80以上、ユーザーに共有を提案）
    APPROVED = "approved"  # 承認済み、公開
    REJECTED = "rejected"  # ユーザーが拒否


class InsightCard(Base):
    """
    Layer 3: Public Plaza のインサイトカード
    匿名化・構造化された知見
    """

    __tablename__ = "insight_cards"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    author_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_log_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("raw_logs.id", ondelete="SET NULL"),
        nullable=True,
    )

    # 構造化コンテンツ
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    context: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    problem: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    solution: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    summary: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    # メタデータ
    topics: Mapped[Optional[List[str]]] = mapped_column(
        ARRAY(String(100)),
        nullable=True,
    )
    tags: Mapped[Optional[List[str]]] = mapped_column(
        ARRAY(String(50)),
        nullable=True,
    )

    # スコアリング
    sharing_value_score: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        nullable=False,
    )
    novelty_score: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        nullable=False,
    )
    generality_score: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        nullable=False,
    )

    # ベクトル埋め込み（Qdrantへの参照ID）
    vector_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )

    # ステータス
    status: Mapped[InsightStatus] = mapped_column(
        SQLEnum(InsightStatus),
        default=InsightStatus.DRAFT,
        nullable=False,
        index=True,
    )

    # エンゲージメント
    view_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    thanks_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    # タイムスタンプ
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )
    published_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    author: Mapped["User"] = relationship(
        "User",
        back_populates="insights",
    )
    source_log: Mapped[Optional["RawLog"]] = relationship(
        "RawLog",
        back_populates="insight",
    )

    def __repr__(self) -> str:
        return f"<InsightCard {self.id}: {self.title[:30]}>"
