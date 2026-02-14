"""
MINDYARD - Deep-Dive Node
課題解決・深掘りを行うノード

BALANCEDモデルを使用して、問題の構造化と解決策の提示を行う。
コンテキスト統合: 履歴・みんなの知恵・プロファイルを全て活用。
"""
from typing import Any, Dict, Optional

from app.core.llm import llm_manager
from app.core.llm_provider import LLMProvider, LLMUsageRole
from app.core.logger import get_traced_logger
from app.services.layer1.conversation_context import (
    build_context_prompt_section,
    format_history_messages,
)

logger = get_traced_logger("DeepDiveNode")

_SYSTEM_PROMPT = """\
あなたは「思考パートナー」です。
答えを出すのではなく、ユーザー自身が洞察を見つける手助けをします。

### 核心思想:
- 急いで解決策を出さない。思考のプロセスにこそ価値がある。
- ユーザーの入力は「磨く前の原石」であり、「チケット」ではない。

### ルール:
1. **確認とリフレーム**: まず理解したことを簡潔に要約し、認識を合わせる。
2. **ギャップを見つける**: ユーザーの思考に足りないもの、曖昧な点、矛盾を見つける。
3. **掘り下げる問い**: 1〜2個の鋭い問いを投げかけ、思考を深める。
   「なぜそう感じるのですか？」
   「もしそれが本当なら、どんな結果になりますか？」
   「ここでの本質的な対立は何ですか？」
4. **構造化**: 思考が散らかっている場合、仮の構造を提案する。
   「この問題には3つの層がありそうです…」

### みんなの知恵が提供された場合:
- チーム内の過去の知見を具体的な根拠として活用する。
- 「チーム内で以前〜で成功した実績があります」のように。

### トーン:
- 知的好奇心。ユーザーの問題に心から興味を持つ。
- 忍耐強く、内省的。日本語で応答。です・ます調。"""


def _get_provider() -> Optional[LLMProvider]:
    try:
        return llm_manager.get_client(LLMUsageRole.BALANCED)
    except Exception:
        return None


async def run_deep_dive_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    深掘りノード: 課題を構造化して解決策を提示
    BALANCEDモデル + 全コンテキスト活用。
    """
    input_text = state["input_text"]
    provider = _get_provider()

    if not provider:
        return {
            "response": "課題を整理してみましょう。もう少し詳しく教えていただけますか？"
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
        logger.info("LLM request", metadata={"prompt_preview": input_text[:100]})
        result = await provider.generate_text(
            messages=messages,
            temperature=0.4,
        )
        logger.info("LLM response", metadata={"response_preview": result.content[:100]})
        return {"response": result.content}
    except Exception as e:
        logger.warning("LLM call failed", metadata={"error": str(e)})
        return {
            "response": "課題を整理してみましょう。もう少し詳しく教えていただけますか？"
        }
