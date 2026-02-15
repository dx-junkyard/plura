"""
PLURA - Conversation Schemas
LangGraph動的ルーティングのためのスキーマ定義

Hypothesis-Driven Intent Routing:
    入力 → 即分類 → 実行 の直線的フローから、
    仮説生成 → 観測（ユーザー反応） → 軌道修正 のループ構造へ。
"""
import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional, List, Literal

from pydantic import BaseModel, Field


class ConversationIntent(str, Enum):
    """会話の意図分類"""
    CHAT = "chat"              # 雑談・カジュアル
    EMPATHY = "empathy"        # 感情的・共感要求
    KNOWLEDGE = "knowledge"    # 知識要求・質問
    DEEP_DIVE = "deep_dive"    # 課題解決・深掘り
    BRAINSTORM = "brainstorm"  # 発想・アイデア出し
    PROBE = "probe"            # 意図確認・仮説検証モード
    STATE_SHARE = "state_share"  # コンディション・状態記録


class PreviousEvaluation(str, Enum):
    """前回のインタラクションに対する暗黙的フィードバック評価"""
    POSITIVE = "positive"   # ユーザーが話題を継続・深掘り・感謝
    NEGATIVE = "negative"   # ユーザーが回答を無視・質問を再提示・トーン変化
    PIVOT = "pivot"         # 明示的に別の話題へ移行
    NONE = "none"           # 前回コンテキストなし（初回ターン）


class IntentHypothesis(BaseModel):
    """仮説駆動型ルーティングの分類結果"""
    previous_evaluation: PreviousEvaluation = Field(
        default=PreviousEvaluation.NONE,
        description="前回インタラクションの暗黙的フィードバック評価",
    )
    primary_intent: ConversationIntent = Field(description="最も可能性の高い意図")
    primary_confidence: float = Field(ge=0.0, le=1.0, description="主仮説の確信度")
    secondary_intent: ConversationIntent = Field(description="次に可能性の高い意図")
    secondary_confidence: float = Field(ge=0.0, le=1.0, description="副仮説の確信度")
    needs_probing: bool = Field(
        default=False,
        description="確信度が低く、ユーザーへの確認が必要か",
    )
    reasoning: str = Field(default="", description="仮説の根拠")


class ResearchPlan(BaseModel):
    """調査計画書（Research Brief）"""
    title: str = Field(description="調査タイトル")
    topic: str = Field(description="具体的な調査主題")
    scope: str = Field(description="対象範囲（地域・年代・分野など）")
    perspectives: List[str] = Field(description="調査の視点・切り口")
    sanitized_query: str = Field(description="個人情報を排除した検索クエリ")


class ConversationRequest(BaseModel):
    """会話リクエスト"""
    message: str = Field(..., min_length=1, description="ユーザー入力テキスト")
    mode_override: Optional[ConversationIntent] = Field(
        None,
        description="モード強制上書き（Mode Switcher機能）",
    )
    research_approved: bool = Field(
        False,
        description="Deep Research の提案フェーズを開始する場合 True",
    )
    research_plan_confirmed: bool = Field(
        False,
        description="調査計画書を確認済みで実行を開始する場合 True",
    )
    research_plan: Optional[Dict[str, Any]] = Field(
        None,
        description="確認済みの調査計画書データ",
    )
    thread_id: Optional[str] = Field(
        None,
        description="会話スレッドID（Deep Research 結果の保存先特定に使用）",
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
    result_log_id: Optional[str] = Field(
        None,
        description="結果が保存される RawLog の ID（ポーリング用）",
    )


class ConversationResponse(BaseModel):
    """会話レスポンス"""
    response: str = Field(description="AIの即時回答")
    intent_badge: IntentBadge = Field(description="判定されたインテントバッジ")
    background_task_info: Optional[Dict[str, Any]] = Field(
        None, 
        description="Deep Research等のノードから直接返却されるタスク情報"
    )
    background_task: Optional[BackgroundTask] = Field(
        None,
        description="非同期タスク情報（Shadow Reply用）",
    )
    user_id: str
    timestamp: datetime = Field(default_factory=datetime.now)
    requires_research_consent: bool = Field(
        default=False,
        description="Deep Research の提案が含まれている場合 True",
    )
    is_researching: bool = Field(
        default=False,
        description="Deep Research が非同期実行中の場合 True",
    )
    research_plan: Optional[ResearchPlan] = Field(
        default=None,
        description="調査計画書（ユーザー確認待ち）",
    )


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
    ConversationIntent.PROBE: {
        "label": "意図を確認中...",
        "icon": "radar",
    },
    ConversationIntent.STATE_SHARE: {
        "label": "コンディション記録",
        "icon": "battery_charging_full",
    },
}
