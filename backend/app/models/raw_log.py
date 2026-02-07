"""
MINDYARD - Raw Log Model
Layer 1: Private Safehouse のログモデル
ユーザーの生の思考・感情を保存する
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
    Float,
    Boolean,
)
from sqlalchemy.dialects.postgresql import UUID, ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, utc_now

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.insight import InsightCard


class LogIntent(str, Enum):
    """
    ユーザーの意図分類
    - LOG: 単に記録したい
    - VENT: 愚痴を言いたい
    - STRUCTURE: 整理したい
    """

    LOG = "log"
    VENT = "vent"
    STRUCTURE = "structure"


class EmotionTag(str, Enum):
    """感情タグ"""

    FRUSTRATED = "frustrated"  # 焦り
    ANGRY = "angry"  # 怒り
    ACHIEVED = "achieved"  # 達成感
    ANXIOUS = "anxious"  # 不安
    CONFUSED = "confused"  # 困惑
    RELIEVED = "relieved"  # 安堵
    EXCITED = "excited"  # 興奮
    NEUTRAL = "neutral"  # 中立


class RawLog(Base):
    """
    Layer 1: Private Logger のログエントリ
    ユーザーの生データを保存する（暗号化対象）
    """

    __tablename__ = "raw_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # コンテンツ
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    content_type: Mapped[str] = mapped_column(
        String(50),
        default="text",  # text, voice, image
        nullable=False,
    )

    # Context Analyzer によるメタデータ
    intent: Mapped[Optional[LogIntent]] = mapped_column(
        SQLEnum(LogIntent),
        nullable=True,
    )
    emotions: Mapped[Optional[List[str]]] = mapped_column(
        ARRAY(String(50)),
        nullable=True,
    )
    emotion_scores: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
    )
    topics: Mapped[Optional[List[str]]] = mapped_column(
        ARRAY(String(100)),
        nullable=True,
    )
    tags: Mapped[Optional[List[str]]] = mapped_column(
        ARRAY(String(50)),
        nullable=True,
    )
    metadata_analysis: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
        comment="ContextAnalyzer による構造化メタデータ",
    )

    # Structural Analyzer による構造的分析結果
    structural_analysis: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
        comment="StructuralAnalyzer による構造的課題分析結果",
    )

    # 処理状態
    is_analyzed: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    is_processed_for_insight: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    is_structure_analyzed: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
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

    # Relationships
    user: Mapped["User"] = relationship(
        "User",
        back_populates="raw_logs",
    )
    insight: Mapped[Optional["InsightCard"]] = relationship(
        "InsightCard",
        back_populates="source_log",
        uselist=False,
    )

    def __repr__(self) -> str:
        return f"<RawLog {self.id} by {self.user_id}>"
