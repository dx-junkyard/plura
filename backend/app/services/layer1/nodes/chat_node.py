"""
MINDYARD - Chit-Chat Node
雑談・カジュアルな会話を処理するノード

気軽で親しみやすいトーンで応答する。
Deep Research 提案のキーワード判定 + LLM 自動判定を内包する。
"""
from typing import Any, Dict, Optional

from app.core.llm import llm_manager
from app.core.llm_provider import LLMProvider, LLMUsageRole
from app.core.logger import get_traced_logger

logger = get_traced_logger("ChatNode")

_SYSTEM_PROMPT = """
You are a friendly and curious chat companion in a Second Brain system.
You handle casual conversation, but you are always looking for "seeds of thought."

### Instructions:
- Respond naturally to greetings and small talk.
- If the user mentions something interesting, show curiosity.
  - User: "I read a book today."
  - You: "Oh, nice. What was the most impressive part?" (Trying to extract insight)
- Maintain a supportive and "Second Brain" persona—always ready to capture ideas.
- Use Japanese naturally.
"""

# ─── Deep Research キーワード判定 ───
# ユーザーの入力にこれらのいずれかが含まれていれば LLM 判定を飛ばして強制 True
_RESEARCH_TRIGGER_KEYWORDS = [
    "調査", "リサーチ", "詳しく", "deep research", "investigate",
    "調べて", "詳細希望", "深掘り", "もっと詳しく", "裏付け",
    "エビデンス", "論文", "データ", "最新情報", "根拠",
    "ファクトチェック", "research", "もう少し知りたい",
]

# LLM に Deep Research を提案すべきか判定させるプロンプト
_RESEARCH_ASSESSMENT_PROMPT = """以下のユーザーの発言と、それに対するチャットの回答を読んでください。
回答の後にさらに専門的な調査（論文・統計・最新ニュース・複数ソースの横断調査等）を行えば
ユーザーにとってプラスになるかどうかを判定してください。

★最重要ルール: 少しでも専門的な調査の余地がある場合は必ず true を返してください。
  迷ったら true です。false にしてよいのは「完全に雑談だけ」の場合のみです。

判定基準（1つでも当てはまれば true）:
- トピックに事実・数値・比較・歴史的背景・最新動向が関係しうる → true
- 回答に「〜と言われています」「一般的には」「おそらく」等の曖昧表現がある → true
- ユーザーが何かを学びたい・解決したい・確認したい意図を持っている → true
- 社会・技術・ビジネス・科学・健康・法律に少しでも関連する → true
- 単純な挨拶（おはよう等）や感情の吐露のみで事実情報が不要 → false

JSON で返してください:
{"should_propose_research": true, "reason": "..."}"""


def _has_research_trigger_keyword(text: str) -> bool:
    """ユーザー入力にリサーチ強制トリガーキーワードが含まれるか"""
    text_lower = text.lower()
    return any(kw in text_lower for kw in _RESEARCH_TRIGGER_KEYWORDS)


async def _assess_research_value_in_chat(
    provider: LLMProvider, input_text: str, response_text: str
) -> bool:
    """LLM でリサーチ提案の要否を判定（chat ノード専用）"""
    try:
        result = await provider.generate_json(
            messages=[
                {"role": "system", "content": _RESEARCH_ASSESSMENT_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"ユーザーの入力:\n{input_text}\n\n"
                        f"AIの回答:\n{response_text}"
                    ),
                },
            ],
            temperature=0.4,
        )
        return bool(result.get("should_propose_research", False))
    except Exception as e:
        logger.warning("Research assessment failed in chat_node", metadata={"error": str(e)})
        return False


def _get_provider() -> Optional[LLMProvider]:
    try:
        return llm_manager.get_client(LLMUsageRole.FAST)
    except Exception:
        return None


async def run_chat_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    雑談ノード: カジュアルな会話に応答

    1. LLM で回答を生成
    2. キーワード判定 → 強制 True / LLM 判定で requires_research_consent を決定
    """
    input_text = state["input_text"]
    provider = _get_provider()

    if not provider:
        return {"response": "なるほど！いいですね。", "requires_research_consent": False}

    try:
        await provider.initialize()
        logger.info("LLM request", metadata={"prompt_preview": input_text[:100]})
        result = await provider.generate_text(
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": input_text},
            ],
            temperature=0.7,
        )
        response_text = result.content
        logger.info("LLM response", metadata={"response_preview": response_text[:100]})

        # --- Deep Research 判定 ---
        if _has_research_trigger_keyword(input_text):
            logger.info("Research trigger: keyword match", metadata={"input_preview": input_text[:80]})
            requires_research = True
        else:
            requires_research = await _assess_research_value_in_chat(
                provider, input_text, response_text
            )
            logger.info("Research assessment result", metadata={"requires": requires_research})

        return {
            "response": response_text,
            "requires_research_consent": requires_research,
        }
    except Exception as e:
        logger.warning("LLM call failed", metadata={"error": str(e)})
        return {"response": "なるほど！いいですね。", "requires_research_consent": False}
