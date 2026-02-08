"""
MINDYARD - Knowledge & Async Trigger Node
知識要求に即座に回答しつつ、必要に応じてCeleryで深掘り調査をキックするノード

UXポイント:
- 同期処理: LLMで即座に回答を生成し、ユーザーを待たせない
- 非同期トリガー: 深い調査が必要な場合、Celeryタスクをキック
- フックメッセージ: 「詳細な裏付け情報を調査中です...」を添える
"""
import logging
from typing import Any, Dict, Optional

from app.core.llm import llm_manager
from app.core.llm_provider import LLMProvider, LLMUsageRole

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """あなたはMINDYARDのナレッジアシスタントです。
ユーザーの知識要求に対して、正確で分かりやすい回答を提供してください。

ルール:
- 簡潔かつ正確に回答する
- 確信がない場合は「〜と考えられています」等の表現を使う
- 専門用語は噛み砕いて説明する
- 日本語で応答する
"""

_DEEP_RESEARCH_PROMPT = """以下のユーザーの質問について、詳細な調査（論文検索、データ収集等）が必要かどうかを判定してください。

判定基準:
- 一般的な知識で回答できる → false
- 最新のデータや専門的な文献が必要 → true
- 定量的なエビデンスが求められている → true
- 複数の情報源を横断的に調べる必要がある → true

必ず以下のJSON形式で応答してください:
{
    "requires_deep_research": true | false,
    "reason": "判定理由"
}"""


def _get_provider() -> Optional[LLMProvider]:
    try:
        return llm_manager.get_client(LLMUsageRole.FAST)
    except Exception:
        return None


async def _check_requires_deep_research(
    provider: LLMProvider, input_text: str
) -> bool:
    """深い調査が必要かどうかを判定"""
    try:
        result = await provider.generate_json(
            messages=[
                {"role": "system", "content": _DEEP_RESEARCH_PROMPT},
                {"role": "user", "content": input_text},
            ],
            temperature=0.1,
        )
        return bool(result.get("requires_deep_research", False))
    except Exception as e:
        logger.warning(f"Deep research check failed: {e}")
        return False


async def run_knowledge_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    知識ノード: 即時回答 + 非同期調査トリガー

    1. LLMで即座に回答を生成
    2. 深掘り調査が必要かを判定
    3. 必要であればCeleryタスクをキックし、background_taskをstateに設定
    """
    input_text = state["input_text"]
    user_id = state.get("user_id", "")
    provider = _get_provider()

    if not provider:
        return {
            "response": "お調べします。少々お待ちください。",
            "background_task_info": None,
        }

    try:
        await provider.initialize()

        # A. 即時回答の生成
        answer_result = await provider.generate_text(
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": input_text},
            ],
            temperature=0.3,
        )
        quick_answer = answer_result.content

        # B. 深掘り調査が必要か判定し、必要ならCeleryに投げる
        needs_research = await _check_requires_deep_research(provider, input_text)

        background_task_info = None
        if needs_research:
            try:
                from app.workers.tasks import deep_research_task

                task = deep_research_task.delay(
                    query=input_text,
                    user_id=user_id,
                )
                background_task_info = {
                    "task_id": task.id,
                    "task_type": "deep_research",
                    "status": "queued",
                    "message": "詳細な裏付け情報を現在バックグラウンドで調査中です...",
                }
                quick_answer += (
                    "\n\n(※詳細な裏付け情報を現在バックグラウンドで調査中です...)"
                )
            except Exception as e:
                logger.warning(f"Failed to dispatch deep_research_task: {e}")

        return {
            "response": quick_answer,
            "background_task_info": background_task_info,
        }

    except Exception as e:
        logger.warning(f"Knowledge node LLM call failed: {e}")
        return {
            "response": "お調べします。少々お待ちください。",
            "background_task_info": None,
        }
