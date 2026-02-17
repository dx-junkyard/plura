"""
PLURA - Project Model
Flash Team Formation で提案されたプロジェクトの永続化モデル
"""
import uuid
from datetime import datetime
from typing import Optional, List, TYPE_CHECKING

from sqlalchemy import String, Text, DateTime, ForeignKey, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from app.db.base import Base, utc_now

if TYPE_CHECKING:
    from app.models.user import User


class ProjectStatus(str, enum.Enum):
    """プロジェクトのステータス"""
    PROPOSED = "proposed"
    ACTIVE = "active"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class Project(Base):
    """Flash Team プロジェクト"""

    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default=ProjectStatus.PROPOSED.value,
        nullable=False,
        index=True,
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    recommendation_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        nullable=True,
        comment="元となった Recommendation の ID",
    )
    team_members: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        comment="チームメンバー [{user_id, display_name, role, avatar_url}]",
    )
    topics: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
    )
    reason: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="AIによるチーム編成理由",
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

    creator: Mapped["User"] = relationship("User", foreign_keys=[created_by])

    def __repr__(self) -> str:
        return f"<Project {self.id} name={self.name}>"
