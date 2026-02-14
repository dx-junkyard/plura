"""
MINDYARD - Chit-Chat Node
雑談・カジュアルな会話を処理するノード

気軽で親しみやすいトーンで応答する。
コンテキスト統合: スレッド履歴とプロファイルを活用して話題を発展させる。
"""
from typing import Any, Dict, Optional

from app.core.llm import llm_manager
from app.core.llm_provider import LLMProvider, LLMUsageRole
from app.core.logger import get_traced_logger
from app.services.layer1.conversation_context import (
    build_context_prompt_section,
    format_history_messages,
)

logger = get_traced_logger("ChatNode")

_SYSTEM_PROMPT = """\
あなたは知的好奇心旺盛な「思考パートナー」です。
気軽な雑談の中でも、相手の言葉から「思考の種」を見つけ出します。

### ルール:
- 挨拶や雑談には自然に応答する。
- 相手が何か面白いことに触れたら、好奇心を示して掘り下げる。
  例: 「今日本を読んだ」→「お、いいですね。一番印象に残った部分は？」
- 相手の発言の核を捉え、具体的な言葉やキーワードで応答する。
- 返答は2〜3文。「受け止め＋洞察 or 具体的な切り口の提示」の構成。
- 会話履歴を踏まえ、文脈を発展させる。同じ質問を繰り返さない。
- 日本語で応答する。です・ます調。

### 禁止:
- 「どのような分野に興味がありますか？」のような汎用テンプレート質問
- 相手の発言をオウム返しして「〜なんですね！」とだけ返す
- 具体性ゼロの抽象的な返答（「面白いですね」で止まる）"""


def _get_provider() -> Optional[LLMProvider]:
    try:
        return llm_manager.get_client(LLMUsageRole.FAST)
    except Exception:
        return None


async def run_chat_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    雑談ノード: カジュアルな会話に応答
    コンテキスト（履歴・プロファイル）を活用して会話を発展させる。
    """
    input_text = state["input_text"]
    provider = _get_provider()

    if not provider:
        return {"response": "なるほど！いいですね。"}

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

    # メッセージ構築: system + 履歴 + 今回の発話
    messages = [{"role": "system", "content": system_prompt}]
    if thread_history:
        messages.extend(format_history_messages(thread_history))
    messages.append({"role": "user", "content": input_text})

    try:
        await provider.initialize()
        logger.info("LLM request", metadata={"prompt_preview": input_text[:100]})
        result = await provider.generate_text(
            messages=messages,
            temperature=0.7,
        )
        logger.info("LLM response", metadata={"response_preview": result.content[:100]})
        return {"response": result.content}
    except Exception as e:
        logger.warning("LLM call failed", metadata={"error": str(e)})
        return {"response": "なるほど！いいですね。"}
