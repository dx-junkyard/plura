"""
MINDYARD - Conversation Schemas
LangGraph動的ルーティングのためのスキーマ定義
"""
import uuid
from datetime import datetime
from enum import Enum
from typing import Optional, List, Literal

from pydantic import BaseModel, Field


class ConversationIntent(str, Enum):
    """会話の意図分類"""
    CHAT = "chat"              # 雑談・カジュアル
    EMPATHY = "empathy"        # 感情的・共感要求
    KNOWLEDGE = "knowledge"    # 知識要求・質問
    DEEP_DIVE = "deep_dive"    # 課題解決・深掘り
    BRAINSTORM = "brainstorm"  # 発想・アイデア出し


class ConversationRequest(BaseModel):
    """会話リクエスト"""
    message: str = Field(..., min_length=1, description="ユーザー入力テキスト")
    mode_override: Optional[ConversationIntent] = Field(
        None,
        description="モード強制上書き（Mode Switcher機能）",
    )


class IntentBadge(BaseModel):
    """Intent Badge - ルーターの判定結果を可視化"""
    intent: ConversationIntent
    confidence: float = Field(ge=0.0, le=1.0)
    label: str = Field(description="UIに表示するラベル")
    icon: str = Field(description="UIに表示するアイコン識別子")


class BackgroundTask(BaseModel):
    """非同期バックグラウンドタスクの情報"""
    task_id: str
    task_type: str
    status: Literal["queued", "running", "completed", "failed"] = "queued"
    message: str = Field(description="ユーザーに表示するメッセージ")


class ConversationResponse(BaseModel):
    """会話レスポンス"""
    response: str = Field(description="AIの即時回答")
    intent_badge: IntentBadge = Field(description="判定されたインテントバッジ")
    background_task: Optional[BackgroundTask] = Field(
        None,
        description="非同期タスク情報（Shadow Reply用）",
    )
    user_id: str
    timestamp: datetime = Field(default_factory=datetime.now)


# Intent Badge のラベル・アイコン定義
INTENT_DISPLAY_MAP = {
    ConversationIntent.CHAT: {
        "label": "雑談モード",
        "icon": "chat_bubble",
    },
    ConversationIntent.EMPATHY: {
        "label": "共感モードで傾聴中...",
        "icon": "heart",
    },
    ConversationIntent.KNOWLEDGE: {
        "label": "知識検索モードで思考中...",
        "icon": "search",
    },
    ConversationIntent.DEEP_DIVE: {
        "label": "深掘りモードで思考中...",
        "icon": "psychology",
    },
    ConversationIntent.BRAINSTORM: {
        "label": "ブレインストーミングモード",
        "icon": "lightbulb",
    },
}
