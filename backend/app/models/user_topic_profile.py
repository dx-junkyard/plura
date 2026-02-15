"""
PLURA - User Topic Profile Model
ユーザーごとのトピック別知識レベル・関心度を管理するテーブル
将来的なパーソナライズのためにテーブル定義を先行実装
"""
import uuid
from datetime import datetime

from sqlalchemy import String, Integer, DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base, utc_now


class UserTopicProfile(Base):
    __tablename__ = "user_topic_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), primary_key=True
    )
    topic: Mapped[str] = mapped_column(String(100), primary_key=True)

    # AIによる推定スコア (1-5)
    knowledge_level: Mapped[int] = mapped_column(Integer, default=1)
    interest_level: Mapped[int] = mapped_column(Integer, default=1)
    purpose_clarity: Mapped[int] = mapped_column(Integer, default=1)

    summary_text: Mapped[str] = mapped_column(Text, nullable=True)
    last_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )

    def __repr__(self) -> str:
        return f"<UserTopicProfile {self.topic} for {self.user_id}>"
