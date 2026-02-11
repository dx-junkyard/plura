"""
MINDYARD - Knowledge Node (対話型ディープ・リサーチ対応)
知識要求に対して内部知識（Layer 3）を検索し回答を生成。
内部情報だけでは不十分な場合、追加調査の提案を行う。

UXポイント:
- 同期処理: まず内部DB（ベクトル検索）の結果で即時回答を生成
- 調査提案: 内部情報だけでは不十分な場合、外部ディープ・リサーチを提案
- ユーザー承認: 提案を受諾した場合のみ、research_trigger_node で非同期調査を発火
"""
from typing import Any, Dict, List, Optional

from app.core.llm import llm_manager
from app.core.llm_provider import LLMProvider, LLMUsageRole
from app.core.logger import get_traced_logger

logger = get_traced_logger("KnowledgeNode")

_SYSTEM_PROMPT = """あなたはMINDYARDのナレッジアシスタントです。
ユーザーの知識要求に対して、正確で分かりやすい回答を提供してください。

ルール:
- 簡潔かつ正確に回答する
- 確信がない場合は「〜と考えられています」等の表現を使う
- 専門用語は噛み砕いて説明する
- 日本語で応答する
"""

_KNOWLEDGE_ANSWER_PROMPT = """あなたはMINDYARDのナレッジアシスタントです。
ユーザーの質問に対して、以下の内部知識ベースの検索結果を参考にしつつ回答してください。

## 内部知識ベースからの検索結果:
{knowledge_context}

## ルール:
- 検索結果に関連する情報がある場合は積極的に引用する
- 検索結果がない場合や関連性が低い場合は、一般知識で回答する
- 確信がない場合は「〜と考えられています」等の表現を使う
- 日本語で応答する
"""

_SUFFICIENCY_CHECK_PROMPT = """以下のユーザーの質問と、内部知識ベースの検索結果を評価してください。

ユーザーの質問: {query}

内部知識ベースの検索結果:
{knowledge_context}

生成した回答:
{answer}

以下の観点で判定してください:
- 内部知識だけでユーザーの質問に十分に回答できているか
- 最新の外部データや専門的な文献が必要か
- ユーザーの問いが広範で、追加調査が有益か

必ず以下のJSON形式で応答してください:
{{
    "is_sufficient": true | false,
    "reason": "判定理由",
    "suggested_research_query": "外部調査が必要な場合の検索クエリ（不要ならnull）"
}}"""


def _get_provider() -> Optional[LLMProvider]:
    try:
        return llm_manager.get_client(LLMUsageRole.FAST)
    except Exception:
        return None


def _format_knowledge_results(results: List[Dict]) -> str:
    """ベクトル検索結果をプロンプト用テキストに整形"""
    if not results:
        return "（関連する内部知識は見つかりませんでした）"

    parts = []
    for i, item in enumerate(results, 1):
        title = item.get("title", "無題")
        summary = item.get("summary", "")
        topics = ", ".join(item.get("topics", []))
        score = item.get("score", 0)
        parts.append(
            f"[{i}] {title} (関連度: {score:.2f})\n"
            f"    要約: {summary}\n"
            f"    トピック: {topics}"
        )
    return "\n".join(parts)


async def _search_internal_knowledge(query: str) -> List[Dict]:
    """Layer 3 のベクトル検索で内部知識を検索"""
    try:
        from app.services.layer3.knowledge_store import knowledge_store
        await knowledge_store.initialize()
        results = await knowledge_store.search_similar(
            query=query,
            limit=5,
            score_threshold=0.5,
        )
        return results
    except Exception as e:
        logger.warning("Internal knowledge search failed", metadata={"error": str(e)})
        return []


async def _check_sufficiency(
    provider: LLMProvider,
    query: str,
    knowledge_context: str,
    answer: str,
) -> Dict[str, Any]:
    """内部知識の回答が十分かどうかを判定"""
    try:
        prompt = _SUFFICIENCY_CHECK_PROMPT.format(
            query=query,
            knowledge_context=knowledge_context,
            answer=answer,
        )
        result = await provider.generate_json(
            messages=[
                {"role": "system", "content": "あなたは回答の充足度を判定するアシスタントです。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
        )
        return {
            "is_sufficient": bool(result.get("is_sufficient", True)),
            "reason": result.get("reason", ""),
            "suggested_research_query": result.get("suggested_research_query"),
        }
    except Exception as e:
        logger.warning("Sufficiency check failed", metadata={"error": str(e)})
        return {"is_sufficient": True, "reason": "", "suggested_research_query": None}


async def run_knowledge_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    知識ノード: 内部知識検索 + 回答生成 + 追加調査提案

    1. Layer 3 ベクトル検索で内部知識を取得
    2. LLM で内部知識を踏まえた回答を生成
    3. requires_deep_research フラグが立っている場合、回答の充足度を判定
    4. 不十分な場合は追加調査の提案メッセージを付加し、状態に記録
    """
    input_text = state["input_text"]
    user_id = state.get("user_id", "")
    requires_deep_research = state.get("requires_deep_research", False)
    provider = _get_provider()

    if not provider:
        return {
            "response": "お調べします。少々お待ちください。",
            "background_task_info": None,
        }

    try:
        await provider.initialize()

        # A. Layer 3 内部知識検索
        logger.info("Searching internal knowledge base", metadata={"query_preview": input_text[:100]})
        knowledge_results = await _search_internal_knowledge(input_text)
        knowledge_context = _format_knowledge_results(knowledge_results)
        logger.info(
            "Internal knowledge search completed",
            metadata={"result_count": len(knowledge_results)},
        )

        # B. 内部知識を踏まえた即時回答の生成
        system_prompt = _KNOWLEDGE_ANSWER_PROMPT.format(
            knowledge_context=knowledge_context,
        )
        logger.info("LLM request (knowledge answer)", metadata={"prompt_preview": input_text[:100]})
        answer_result = await provider.generate_text(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": input_text},
            ],
            temperature=0.3,
        )
        quick_answer = answer_result.content
        logger.info("LLM response (knowledge answer)", metadata={"response_preview": quick_answer[:100]})

        # C. 追加調査の提案判定（requires_deep_research フラグが立っている場合）
        research_offered = False
        pending_research_query = None

        if requires_deep_research:
            sufficiency = await _check_sufficiency(
                provider, input_text, knowledge_context, quick_answer,
            )
            logger.info(
                "Sufficiency check result",
                metadata={
                    "is_sufficient": sufficiency["is_sufficient"],
                    "reason": sufficiency["reason"],
                },
            )

            if not sufficiency["is_sufficient"]:
                # 追加調査の提案をメッセージ末尾に付加
                research_query = sufficiency.get("suggested_research_query") or input_text
                proposal_message = (
                    "\n\n---\n"
                    "💡 **今の私の知識（DB）ではここまで分かっています。**"
                    "さらに最新の情報を外部から詳しく調べましょうか？\n"
                    "「お願い」と言っていただければ、ディープ・リサーチを開始します。"
                )
                quick_answer += proposal_message
                research_offered = True
                pending_research_query = research_query
                logger.info(
                    "Research proposal offered",
                    metadata={"research_query": research_query[:100]},
                )

        return {
            "response": quick_answer,
            "background_task_info": None,
            "research_offered": research_offered,
            "pending_research_query": pending_research_query,
        }

    except Exception as e:
        logger.warning("LLM call failed", metadata={"error": str(e)})
        return {
            "response": "お調べします。少々お待ちください。",
            "background_task_info": None,
        }
