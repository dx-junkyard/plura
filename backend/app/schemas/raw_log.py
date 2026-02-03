"""
MINDYARD - Raw Log Schemas
Layer 1: Private Logger のスキーマ
"""
import uuid
from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, Field

from app.models.raw_log import LogIntent, EmotionTag


class RawLogBase(BaseModel):
    """ログ基底スキーマ"""

    content: str = Field(..., min_length=1)
    content_type: str = Field(default="text")


class RawLogCreate(RawLogBase):
    """ログ作成スキーマ"""

    pass


class RawLogUpdate(BaseModel):
    """ログ更新スキーマ"""

    content: Optional[str] = None


class RawLogResponse(RawLogBase):
    """ログレスポンススキーマ"""

    id: uuid.UUID
    user_id: uuid.UUID
    intent: Optional[LogIntent] = None
    emotions: Optional[List[str]] = None
    emotion_scores: Optional[dict] = None
    topics: Optional[List[str]] = None
    structural_analysis: Optional[dict] = None
    is_analyzed: bool
    is_processed_for_insight: bool
    is_structure_analyzed: bool = False
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RawLogListResponse(BaseModel):
    """ログリストレスポンス"""

    items: List[RawLogResponse]
    total: int
    page: int
    page_size: int


class AckResponse(BaseModel):
    """
    ノン・ジャッジメンタル応答
    「聞く」ことに徹した受容的な相槌
    """

    message: str
    log_id: uuid.UUID
    timestamp: datetime

    @classmethod
    def create_ack(cls, log_id: uuid.UUID, intent: Optional[LogIntent] = None) -> "AckResponse":
        """意図に応じた相槌を生成"""
        ack_messages = {
            LogIntent.LOG: [
                "記録しました。",
                "受け取りました。",
            ],
            LogIntent.VENT: [
                "それは大変でしたね。",
                "お気持ち、受け止めました。",
                "聞かせてくれてありがとうございます。",
            ],
            LogIntent.STRUCTURE: [
                "整理を始めますね。",
                "承知しました。",
            ],
            None: [
                "受領しました。",
            ],
        }

        import random
        messages = ack_messages.get(intent, ack_messages[None])
        message = random.choice(messages)

        return cls(
            message=message,
            log_id=log_id,
            timestamp=datetime.now()
        )
