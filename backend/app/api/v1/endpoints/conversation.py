"""
PLURA - Conversation Endpoints
LangGraph動的ルーティングによる会話API

UX機能:
- Intent Badge: 判定されたインテントをバッジとして返却
- Shadow Reply: 非同期タスクの情報を返却（フロントで可視化）
- Mode Switcher: mode_overrideでインテントを強制上書き
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.base import get_async_session
from app.models.user import User
from app.schemas.conversation import (
    ConversationRequest,
    ConversationResponse,
)
from app.services.layer1.conversation_graph import run_conversation

router = APIRouter()


@router.post("/", response_model=ConversationResponse)
async def converse(
    request: ConversationRequest,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
):
    """
    会話エンドポイント: LangGraphで意図を分類し、適切なノードで応答を生成

    リクエスト: {"message": "...", "mode_override": "empathy" (optional), "research_approved": false}
    - 自動モード: messageからAIが意図を判定して最適なノードへルーティング
    - 手動モード: mode_overrideで意図を強制指定（/vent, /idea 等のスラッシュコマンド対応）
    - Deep Research: research_approved=true でリサーチ実行

    レスポンスには以下が含まれる:
    - response: AIの即時回答
    - intent_badge: 判定されたインテント情報（UI表示用）
    - background_task: 非同期タスク情報（Shadow Reply用、knowledgeノード時のみ）
    - requires_research_consent: Deep Research 提案フラグ
    """
    try:
        result = await run_conversation(
            input_text=request.message,
            user_id=str(current_user.id),
            mode_override=request.mode_override.value if request.mode_override else None,
            research_approved=request.research_approved,
            research_plan_confirmed=request.research_plan_confirmed,
            research_plan=request.research_plan,
            thread_id=request.thread_id,
        )
        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"会話処理中にエラーが発生しました: {str(e)}",
        )
