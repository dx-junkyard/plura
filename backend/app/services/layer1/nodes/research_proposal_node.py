"""
PLURA - Research Proposal Node
調査計画書（Research Brief）を生成するノード

「Deep Research を実行する」ボタン押下後の最初のフェーズ。
会話履歴を分析し、個人情報を排除・調査条件を構造化した
「調査計画書」を即座に作成してユーザーに提示する。
ユーザーが確認・承認した後に初めて deep_research_node が実行される。
"""
from typing import Any, Dict, Optional

from app.core.llm import llm_manager
from app.core.llm_provider import LLMProvider, LLMUsageRole
from app.core.logger import get_traced_logger

logger = get_traced_logger("ResearchProposalNode")

_PROPOSAL_PROMPT = """あなたは PLURA の Deep Research プランナーです。
ユーザーの会話履歴（入力とAIの回答）を分析し、
**個人的な文脈を排除した客観的な調査計画書**を作成してください。

### 重要ルール:
1. 個人を特定できる情報（「私の会社の〜」「来週の会議で〜」等）は削除し、
   一般的かつ客観的な調査クエリに変換すること。
2. 調査の目的・範囲・視点を明確に構造化すること。
3. sanitized_query は Deep Research に直接渡す検索クエリとして最適化すること。

### 出力（必ず JSON）:
{
  "title": "調査タイトル（30文字以内）",
  "topic": "具体的な調査主題（100文字以内）",
  "scope": "対象範囲（地域・年代・分野など）",
  "perspectives": ["視点1", "視点2", "視点3"],
  "sanitized_query": "Deep Research へ渡す純化された検索クエリ（個人情報を完全に排除）"
}

### 注意:
- perspectives は 2〜4 個程度にする
- sanitized_query は日本語で、200文字以内に収める
- 元の質問の意図を損なわないようにする
"""


def _get_provider() -> Optional[LLMProvider]:
    try:
        return llm_manager.get_client(LLMUsageRole.FAST)
    except Exception:
        return None


async def run_research_proposal_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    調査計画書を生成するノード

    1. FAST モデルで会話内容から調査計画を生成
    2. 個人情報の排除と調査条件の構造化を実施
    3. ユーザーが確認できる形式でレスポンスを返す
    """
    input_text = state["input_text"]
    previous_response = state.get("previous_response", "")

    provider = _get_provider()
    if not provider:
        return {
            "response": (
                "申し訳ありません。調査計画の作成に失敗しました。\n"
                "もう一度お試しください。"
            ),
            "research_plan": None,
        }

    try:
        await provider.initialize()

        user_content = f"ユーザーの入力:\n{input_text}"
        if previous_response:
            user_content += f"\n\nAIの回答:\n{previous_response}"

        logger.info(
            "Generating research proposal",
            metadata={"input_preview": input_text[:100]},
        )

        plan = await provider.generate_json(
            messages=[
                {"role": "system", "content": _PROPOSAL_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0.3,
        )

        # バリデーション: 必須フィールドが揃っているか
        required_keys = {"title", "topic", "scope", "perspectives", "sanitized_query"}
        if not required_keys.issubset(plan.keys()):
            logger.warning(
                "Research proposal missing fields",
                metadata={"keys": list(plan.keys())},
            )
            # 不足分をフォールバックで埋める
            plan.setdefault("title", "調査計画")
            plan.setdefault("topic", input_text[:100])
            plan.setdefault("scope", "指定なし")
            plan.setdefault("perspectives", ["概要調査"])
            plan.setdefault("sanitized_query", input_text[:200])

        # perspectives を文字列リストに正規化
        if not isinstance(plan.get("perspectives"), list):
            plan["perspectives"] = [str(plan.get("perspectives", "概要調査"))]

        # UI 表示用テキストを生成
        perspectives_text = "、".join(plan["perspectives"])
        response_text = (
            f"以下の内容で詳細調査を行います。よろしいですか？\n\n"
            f"**調査計画**\n"
            f"- **主題**: {plan['topic']}\n"
            f"- **範囲**: {plan['scope']}\n"
            f"- **視点**: {perspectives_text}\n\n"
            f"「調査を開始する」ボタンで実行します。"
        )

        logger.info(
            "Research proposal generated",
            metadata={
                "title": plan["title"],
                "sanitized_query_preview": plan["sanitized_query"][:80],
            },
        )

        return {
            "response": response_text,
            "research_plan": plan,
        }

    except Exception as e:
        logger.warning(
            "Research proposal generation failed",
            metadata={"error": str(e)},
        )
        # フォールバック: 入力をそのまま簡易プランにする
        fallback_plan = {
            "title": "調査計画",
            "topic": input_text[:100],
            "scope": "指定なし",
            "perspectives": ["概要調査"],
            "sanitized_query": input_text[:200],
        }
        return {
            "response": (
                f"調査計画を自動生成できませんでした。以下の内容で調査を行いますか？\n\n"
                f"**調査計画**\n"
                f"- **主題**: {fallback_plan['topic']}\n\n"
                f"「調査を開始する」ボタンで実行します。"
            ),
            "research_plan": fallback_plan,
        }
