"""
PLURA - User State Model
ユーザーのコンディション（体調・気分・集中度）を時系列で保存する軽量テーブル
"""
import uuid
from datetime import datetime

from sqlalchemy import String, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base, utc_now


class UserState(Base):
    __tablename__ = "user_states"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )

    # 状態の種類 (例: energy, mood, focus)
    state_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # 値 (例: low, tired, high など)
    value: Mapped[str] = mapped_column(String(50), nullable=False)
    # 自由記述メモ
    note: Mapped[str] = mapped_column(String(200), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )

    def __repr__(self) -> str:
        return f"<UserState {self.state_type}={self.value} by {self.user_id}>"
