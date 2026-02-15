"""
PLURA - User Model
ユーザー管理モデル
"""
import uuid
from datetime import datetime
from typing import Optional, List, TYPE_CHECKING

from sqlalchemy import String, Boolean, DateTime, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, utc_now

if TYPE_CHECKING:
    from app.models.raw_log import RawLog
    from app.models.insight import InsightCard


class User(Base):
    """ユーザーモデル"""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False,
    )
    hashed_password: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    display_name: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )
    avatar_url: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    is_verified: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
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

    # Relationships
    raw_logs: Mapped[List["RawLog"]] = relationship(
        "RawLog",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    insights: Mapped[List["InsightCard"]] = relationship(
        "InsightCard",
        back_populates="author",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<User {self.email}>"
