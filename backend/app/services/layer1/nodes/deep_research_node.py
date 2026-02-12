"""
MINDYARD - Deep Research Node
Celery タスクをキックし、即座にレスポンスを返すノード

ユーザーの承認後に実行され、非同期で詳細リサーチを開始する。
結果は Celery タスク内で RawLog の assistant_reply に保存される。
"""
import uuid
from typing import Any, Dict

from app.core.logger import get_traced_logger

logger = get_traced_logger("DeepResearchNode")


async def run_deep_research_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Deep Research ノード: Celery タスクをキックして即座に返す

    1. 結果保存用の RawLog ID を事前生成
    2. run_deep_research_task を .delay() でキック
    3. 「調査を開始しました」メッセージと background_task_info を即座に返す
    """
    user_id = state.get("user_id", "")
    thread_id = state.get("thread_id", "")
    previous_response = state.get("previous_response", "")

    # 確定済み調査計画書がある場合は sanitized_query を使用（個人情報排除済み）
    research_plan = state.get("research_plan")
    if research_plan and isinstance(research_plan, dict):
        input_text = research_plan.get("sanitized_query", state["input_text"])
    else:
        input_text = state["input_text"]

    # 結果保存先の RawLog ID を事前生成
    research_log_id = str(uuid.uuid4())

    try:
        # Celery タスクをキック（非同期で実行される）
        from app.workers.tasks import run_deep_research_task

        task = run_deep_research_task.delay(
            user_id,
            thread_id or "",
            input_text,
            previous_response,
            research_log_id,
        )

        logger.info(
            "Deep Research task kicked",
            metadata={
                "task_id": task.id,
                "research_log_id": research_log_id,
                "query_preview": input_text[:100],
            },
        )

        return {
            "response": (
                "調査を開始しました。完了までしばらくお待ちください。\n"
                "結果は自動的に表示されます。"
            ),
            "background_task_info": {
                "task_id": task.id,
                "task_type": "deep_research",
                "status": "queued",
                "message": "Deep Research を実行中です",
                "result_log_id": research_log_id,
            },
        }

    except Exception as e:
        logger.warning(
            "Failed to kick deep research task",
            metadata={"error": str(e)},
        )
        return {
            "response": (
                "申し訳ありません。Deep Research の開始に失敗しました。\n"
                "しばらく待ってから再度お試しください。"
            ),
        }
