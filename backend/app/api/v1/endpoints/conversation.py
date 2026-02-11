"""
MINDYARD - Conversation Endpoints
LangGraph動的ルーティングによる会話API

UX機能:
- Intent Badge: 判定されたインテントをバッジとして返却
- Shadow Reply: 非同期タスクの情報を返却（フロントで可視化）
- Mode Switcher: mode_overrideでインテントを強制上書き
"""
import time

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.logger import get_traced_logger
from app.db.base import get_async_session
from app.models.user import User
from app.schemas.conversation import (
    ConversationRequest,
    ConversationResponse,
)
from app.services.layer1.conversation_graph import run_conversation

logger = get_traced_logger("ConversationAPI")

router = APIRouter()


@router.post("/", response_model=ConversationResponse)
async def converse(
    request: ConversationRequest,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
):
    """
    会話エンドポイント: LangGraphで意図を分類し、適切なノードで応答を生成

    リクエスト: {"message": "...", "mode_override": "empathy" (optional)}
    - 自動モード: messageからAIが意図を判定して最適なノードへルーティング
    - 手動モード: mode_overrideで意図を強制指定（/vent, /idea 等のスラッシュコマンド対応）

    レスポンスには以下が含まれる:
    - response: AIの即時回答
    - intent_badge: 判定されたインテント情報（UI表示用）
    - background_task: 非同期タスク情報（Shadow Reply用、knowledgeノード時のみ）
    """
    user_id = str(current_user.id)
    mode_override = request.mode_override.value if request.mode_override else None

    logger.info(
        "POST /api/v1/conversation/ - Request received",
        metadata={
            "user_id": user_id,
            "message_length": len(request.message),
            "message_preview": request.message[:100],
            "mode_override": mode_override,
        },
    )
    start_time = time.monotonic()

    try:
        result = await run_conversation(
            input_text=request.message,
            user_id=user_id,
            mode_override=mode_override,
        )

        duration_ms = round((time.monotonic() - start_time) * 1000, 1)
        logger.info(
            "POST /api/v1/conversation/ - Request completed",
            metadata={
                "user_id": user_id,
                "duration_ms": duration_ms,
                "intent": result.intent_badge.intent.value if result.intent_badge else None,
                "confidence": result.intent_badge.confidence if result.intent_badge else None,
                "has_background_task": result.background_task is not None,
                "response_length": len(result.response) if result.response else 0,
            },
        )
        return result

    except Exception as e:
        duration_ms = round((time.monotonic() - start_time) * 1000, 1)
        logger.exception(
            "POST /api/v1/conversation/ - Request FAILED with exception",
            metadata={
                "user_id": user_id,
                "duration_ms": duration_ms,
                "error_type": type(e).__name__,
                "error": str(e),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"会話処理中にエラーが発生しました: {str(e)}",
        )
