"""
MINDYARD - Research Trigger Node (承認用ノード)
ユーザーが「お願い」と肯定的に返答した際に、Celeryタスクを発火するノード

UXフロー:
1. knowledge_node が調査を提案し、research_offered=True を設定
2. ユーザーが「お願い」等の肯定的返答をする
3. router が research_trigger ノードへルーティング
4. このノードが deep_research_task.delay() を呼び出す
5. 「承知しました。深層調査を開始します」と返答
"""
from typing import Any, Dict

from app.core.logger import get_traced_logger

logger = get_traced_logger("ResearchTriggerNode")

# ユーザーの肯定的返答を検知するキーワード
_APPROVAL_KEYWORDS = [
    "お願い", "おねがい", "頼む", "たのむ",
    "やって", "調べて", "はい", "うん",
    "ぜひ", "よろしく", "OK", "ok", "Yes", "yes",
    "お願いします", "頼みます", "やってください",
]


def is_research_approval(input_text: str) -> bool:
    """ユーザーの返答がリサーチ承認かどうかを判定"""
    return any(kw in input_text for kw in _APPROVAL_KEYWORDS)


async def run_research_trigger_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    リサーチ・トリガー・ノード: ユーザーの承認を受けてCeleryタスクを発火

    前提条件:
    - state["research_offered"] == True
    - state["pending_research_query"] が設定済み

    処理:
    1. pending_research_query を取得
    2. deep_research_task.delay() でCeleryタスクを発火
    3. 「承知しました。深層調査を開始します」と返答
    """
    pending_query = state.get("pending_research_query", "")
    user_id = state.get("user_id", "")

    if not pending_query:
        logger.warning("Research trigger called without pending_research_query")
        return {
            "response": "調査対象が見つかりませんでした。もう一度質問を教えてください。",
            "research_offered": False,
            "pending_research_query": None,
        }

    logger.info(
        "Research trigger firing",
        metadata={
            "query_preview": pending_query[:100],
            "user_id": user_id,
        },
    )

    background_task_info = None
    try:
        from app.workers.tasks import deep_research_task

        task = deep_research_task.delay(
            query=pending_query,
            user_id=user_id,
        )
        background_task_info = {
            "task_id": task.id,
            "task_type": "deep_research",
            "status": "queued",
            "message": "ディープ・リサーチを実行中です。完了次第お知らせします。",
        }
        logger.info(
            "Deep research task dispatched",
            metadata={"task_id": task.id},
        )
    except Exception as e:
        logger.warning(
            "Failed to dispatch deep_research_task",
            metadata={"error": str(e)},
        )
        return {
            "response": "申し訳ございません。調査の開始に失敗しました。もう一度お試しください。",
            "research_offered": False,
            "pending_research_query": None,
        }

    return {
        "response": (
            "承知しました！深層調査を開始します。"
            "少しお時間をいただきますので、その間に他の作業を進めていてください。"
            "完了次第、このストリームにお知らせしますね。"
        ),
        "background_task_info": background_task_info,
        "research_offered": False,
        "pending_research_query": None,
    }
