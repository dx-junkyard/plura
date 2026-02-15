"""
PLURA - Insight Card Schemas
Layer 3: Public Plaza のスキーマ
"""
import uuid
from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, Field

from app.models.insight import InsightStatus


class InsightCardBase(BaseModel):
    """インサイト基底スキーマ"""

    title: str = Field(..., max_length=255)
    context: Optional[str] = None
    problem: Optional[str] = None
    solution: Optional[str] = None
    summary: str


class InsightCardCreate(InsightCardBase):
    """インサイト作成スキーマ（内部用）"""

    source_log_id: Optional[uuid.UUID] = None
    topics: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    sharing_value_score: float = 0.0
    novelty_score: float = 0.0
    generality_score: float = 0.0


class InsightCardUpdate(BaseModel):
    """インサイト更新スキーマ"""

    title: Optional[str] = None
    context: Optional[str] = None
    problem: Optional[str] = None
    solution: Optional[str] = None
    summary: Optional[str] = None
    status: Optional[InsightStatus] = None


class InsightCardResponse(InsightCardBase):
    """インサイトレスポンススキーマ"""

    id: uuid.UUID
    author_id: uuid.UUID
    topics: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    sharing_value_score: float
    status: InsightStatus
    view_count: int
    thanks_count: int
    created_at: datetime
    updated_at: datetime
    published_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class InsightCardListResponse(BaseModel):
    """インサイトリストレスポンス"""

    items: List[InsightCardResponse]
    total: int
    page: int
    page_size: int


class SharingProposal(BaseModel):
    """
    共有提案スキーマ
    Sharing Broker がユーザーに提示する
    """

    insight: InsightCardResponse
    message: str = Field(
        default="あなたのこの経験は、チームの役に立つ可能性があります。この形式で共有しますか？"
    )
    original_content_preview: Optional[str] = None  # マスク済みの元テキストプレビュー


class SharingDecision(BaseModel):
    """共有判断スキーマ"""

    insight_id: uuid.UUID
    approved: bool
    feedback: Optional[str] = None  # ユーザーからのフィードバック
