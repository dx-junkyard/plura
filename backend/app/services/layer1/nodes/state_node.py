"""
MINDYARD - State Share Node
ユーザーの短い状態共有（眠い、疲れた等）を受け止め、
軽い共感を返しつつ裏側でコンディションデータを保存するノード

過剰な深掘りや分析を行わないことがこのノードの最重要設計方針。
"""
import uuid
from typing import Any, Dict, Optional

from app.core.llm import llm_manager
from app.core.llm_provider import LLMProvider, LLMUsageRole
from app.core.logger import get_traced_logger
from app.db.base import async_session_maker
from app.models.user_state import UserState
from app.models.raw_log import RawLog, LogIntent

logger = get_traced_logger("StateNode")

_SYSTEM_PROMPT = """
You are a caring companion in a Second Brain system.
The user is sharing their current physical or mental condition (e.g., tired, sleepy, hungry).
This is NOT a request for help, advice, or analysis.

### Instructions:
- Respond with a short, warm acknowledgment in Japanese (40 characters max).
- Do NOT ask any questions. Do NOT analyze. Do NOT give advice.
- Simply validate their state with empathy.
- Examples: "お疲れさまです、無理せずに。", "ゆっくり休んでくださいね。"

### Output Format (JSON):
{
    "response": "40文字以内の労いメッセージ",
    "state_type": "energy | mood | focus | comfort | general",
    "value": "状態の値 (例: low, tired, sleepy, hungry)"
}
"""

_FALLBACK_RESPONSES = {
    "energy": "お疲れさまです。無理せず休んでくださいね。",
    "mood": "そうなんですね。ゆっくりいきましょう。",
    "focus": "少し休憩するのもいいかもしれませんね。",
    "comfort": "大変ですね。無理しないでくださいね。",
    "general": "お疲れさまです。記録しておきますね。",
}


def _get_provider() -> Optional[LLMProvider]:
    try:
        return llm_manager.get_client(LLMUsageRole.FAST)
    except Exception:
        return None


async def _save_user_state(
    user_id: str,
    state_type: str,
    value: str,
    note: Optional[str] = None,
) -> None:
    """UserState テーブルにコンディションを保存"""
    try:
        async with async_session_maker() as session:
            user_state = UserState(
                user_id=uuid.UUID(user_id),
                state_type=state_type,
                value=value,
                note=note,
            )
            session.add(user_state)
            await session.commit()
            logger.info(
                "User state saved",
                metadata={"user_id": user_id, "state_type": state_type, "value": value},
            )
    except Exception as e:
        logger.warning("Failed to save user state", metadata={"error": str(e)})


async def _save_raw_log_as_state(user_id: str, content: str) -> None:
    """RawLog に intent=STATE として保存"""
    try:
        async with async_session_maker() as session:
            raw_log = RawLog(
                user_id=uuid.UUID(user_id),
                content=content,
                content_type="text",
                intent=LogIntent.STATE,
                is_analyzed=True,
            )
            session.add(raw_log)
            await session.commit()
            logger.info(
                "Raw log saved as state",
                metadata={"user_id": user_id, "content_preview": content[:50]},
            )
    except Exception as e:
        logger.warning("Failed to save raw log as state", metadata={"error": str(e)})


async def run_state_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    状態共有ノード: ユーザーのコンディションを受け止め、軽い共感を返す

    1. LLMで短い共感メッセージ + 状態分類をJSON生成
    2. UserState にコンディション保存
    3. RawLog に intent=STATE として保存
    """
    input_text = state["input_text"]
    user_id = state.get("user_id", "")

    provider = _get_provider()

    response_text = _FALLBACK_RESPONSES["general"]
    state_type = "general"
    value = "noted"

    if provider:
        try:
            await provider.initialize()
            logger.info("LLM request", metadata={"prompt_preview": input_text[:100]})
            result = await provider.generate_json(
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": input_text},
                ],
                temperature=0.5,
            )
            response_text = result.get("response", _FALLBACK_RESPONSES["general"])
            state_type = result.get("state_type", "general")
            value = result.get("value", "noted")
            logger.info(
                "LLM response",
                metadata={
                    "response_preview": response_text[:100],
                    "state_type": state_type,
                    "value": value,
                },
            )
        except Exception as e:
            logger.warning("LLM call failed, using fallback", metadata={"error": str(e)})

    # バックグラウンドでDB保存（エラーが発生してもレスポンスは返す）
    if user_id:
        await _save_user_state(user_id, state_type, value, note=input_text[:200])
        await _save_raw_log_as_state(user_id, input_text)

    return {"response": response_text}
