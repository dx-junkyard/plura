"""
MINDYARD - Knowledge & Async Trigger Node
知識要求に即座に回答しつつ、必要に応じてCeleryで深掘り調査をキックするノード

コンテキスト統合: みんなの知恵を活用して回答精度を向上。
"""
from typing import Any, Dict, Optional

from app.core.llm import llm_manager
from app.core.llm_provider import LLMProvider, LLMUsageRole
from app.core.logger import get_traced_logger
from app.services.layer1.conversation_context import (
    build_context_prompt_section,
    format_history_messages,
)

logger = get_traced_logger("KnowledgeNode")

_SYSTEM_PROMPT = """\
あなたはMINDYARDのナレッジアシスタントです。
ユーザーの知識要求に対して、正確で分かりやすい回答を提供してください。

### ルール:
- 簡潔かつ正確に回答する
- 確信がない場合は「〜と考えられています」等の表現を使う
- 専門用語は噛み砕いて説明する
- 会話の文脈を踏まえた回答をする（聞き返し禁止）

### みんなの知恵が提供された場合:
- チーム内の知見を回答の根拠として具体的に引用する
- 「チーム内で以前〜という知見がありました」のように自然に組み込む

- 日本語で応答する"""

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


async def run_knowledge_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    知識ノード: 即時回答 + 非同期調査トリガー
    コンテキスト（履歴・みんなの知恵）を活用した精度の高い回答を生成。
    """
    input_text = state["input_text"]
    user_id = state.get("user_id", "")
    provider = _get_provider()

    if not provider:
        return {
            "response": "お調べします。少々お待ちください。",
            "background_task_info": None,
        }

    # コンテキスト構築
    thread_history = state.get("thread_history")
    collective_wisdom = state.get("collective_wisdom")
    profile_summary = state.get("user_profile_summary")
    situation_hint = state.get("situation_hint")

    system_prompt = _SYSTEM_PROMPT
    if situation_hint:
        system_prompt += f"\n\n【今回の状況ヒント】\n{situation_hint}"
    system_prompt += build_context_prompt_section(
        history=thread_history,
        collective_wisdom=collective_wisdom,
        profile_summary=profile_summary,
        input_text=input_text,
    )

    messages = [{"role": "system", "content": system_prompt}]
    if thread_history:
        messages.extend(format_history_messages(thread_history))
    messages.append({"role": "user", "content": input_text})

    try:
        await provider.initialize()

        # A. 即時回答の生成
        logger.info("LLM request (quick answer)", metadata={"prompt_preview": input_text[:100]})
        answer_result = await provider.generate_text(
            messages=messages,
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
