"""
PLURA - Knowledge & Async Trigger Node
知識要求に即座に回答しつつ、必要に応じてCeleryで深掘り調査をキックするノード

UXポイント:
- 同期処理: LLMで即座に回答を生成し、ユーザーを待たせない
- 非同期トリガー: 深い調査が必要な場合、Celeryタスクをキック
- フックメッセージ: 「詳細な裏付け情報を調査中です...」を添える
"""
from typing import Any, Dict, Optional

from app.core.llm import llm_manager
from app.core.llm_provider import LLMProvider, LLMUsageRole
from app.core.logger import get_traced_logger

logger = get_traced_logger("KnowledgeNode")

_SYSTEM_PROMPT = """あなたはPLURAのナレッジアシスタントです。
ユーザーの知識要求に対して、正確で分かりやすい回答を提供してください。

ルール:
- 簡潔かつ正確に回答する
- 確信がない場合は「〜と考えられています」等の表現を使う
- 専門用語は噛み砕いて説明する
- 日本語で応答する
- 「参考ドキュメント」セクションが提供されている場合、その情報を優先的に活用する
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
        logger.warning("Deep research check failed", metadata={"error": str(e)})
        return False


async def _retrieve_private_rag_context(user_id: str, query: str) -> str:
    """Private RAG からユーザーのドキュメントを検索し、コンテキストを構築"""
    try:
        from app.services.layer1.private_rag import private_rag

        results = await private_rag.search(
            query=query,
            user_id=user_id,
            limit=3,
            score_threshold=0.5,
        )
        if not results:
            return ""

        context_parts = ["【参考ドキュメント】"]
        for r in results:
            context_parts.append(
                f"({r['filename']}) {r['text'][:400]}"
            )
        return "\n".join(context_parts)
    except Exception as e:
        logger.warning("Private RAG search failed", metadata={"error": str(e)})
        return ""


async def run_knowledge_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    知識ノード: Private RAG検索 + 即時回答 + 非同期調査トリガー

    1. Private RAG でユーザーのドキュメントから関連情報を検索
    2. LLMで即座に回答を生成（RAG コンテキスト付き）
    3. 深掘り調査が必要かを判定
    4. 必要であればCeleryタスクをキックし、background_taskをstateに設定
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

        # Private RAG コンテキスト取得
        rag_context = await _retrieve_private_rag_context(user_id, input_text)

        # A. 即時回答の生成（RAGコンテキスト付き）
        user_message = input_text
        if rag_context:
            user_message = f"{input_text}\n\n{rag_context}"
            logger.info("Private RAG context found", metadata={"context_length": len(rag_context)})

        logger.info("LLM request (quick answer)", metadata={"prompt_preview": input_text[:100]})
        answer_result = await provider.generate_text(
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            temperature=0.3,
        )
        quick_answer = answer_result.content
        logger.info("LLM response (quick answer)", metadata={"response_preview": quick_answer[:100]})

        # B. 深掘り調査が必要か判定し、必要ならCeleryに投げる
        needs_research = await _check_requires_deep_research(provider, input_text)
        logger.info("Deep research check", metadata={"needs_research": needs_research})

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
        logger.warning("LLM call failed", metadata={"error": str(e)})
        return {
            "response": "お調べします。少々お待ちください。",
            "background_task_info": None,
        }
