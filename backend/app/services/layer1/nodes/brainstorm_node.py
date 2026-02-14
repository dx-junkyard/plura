"""
MINDYARD - Brainstorm Node
アイデア出し・壁打ちを行うノード

創造的な発想を促し、多角的な視点からアイデアを展開する。
コンテキスト統合: 履歴・みんなの知恵を活用して発想を拡張。
"""
from typing import Any, Dict, Optional

from app.core.llm import llm_manager
from app.core.llm_provider import LLMProvider, LLMUsageRole
from app.core.logger import get_traced_logger
from app.services.layer1.conversation_context import (
    build_context_prompt_section,
    format_history_messages,
)

logger = get_traced_logger("BrainstormNode")

_SYSTEM_PROMPT = """\
あなたはMINDYARDのブレインストーミングパートナーです。
ユーザーのアイデアを広げ、新しい視点を提供することが役割です。

### ルール:
- 否定しない。「Yes, and...」の精神で
- アイデアの量を重視する（質は後で整理）
- 異なる角度からの視点を提示する
- 「もし〜だったら？」という仮説を投げかける
- ユーザーのアイデアを発展・拡張させる
- 会話履歴を踏まえて、既出のアイデアと重複しない新しい方向を提示
- 日本語で応答する

### みんなの知恵が提供された場合:
- チーム内の知見をアイデアの種として活用する
- 「チーム内でこんな事例がありました」のように自然に言及

### フォーマット:
- アイデアは箇条書きで列挙
- 各アイデアに一言で「狙い」を添える
- 最後に「さらに広げるなら？」という問いかけを入れる"""


def _get_provider() -> Optional[LLMProvider]:
    try:
        return llm_manager.get_client(LLMUsageRole.BALANCED)
    except Exception:
        return None


async def run_brainstorm_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    ブレインストーミングノード: 創造的な発想を展開
    BALANCEDモデル + コンテキスト活用。
    """
    input_text = state["input_text"]
    provider = _get_provider()

    if not provider:
        return {
            "response": "面白いアイデアですね！もう少し詳しく聞かせてもらえますか？"
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
            temperature=0.8,
        )
        logger.info("LLM response", metadata={"response_preview": result.content[:100]})
        return {"response": result.content}
    except Exception as e:
        logger.warning("LLM call failed", metadata={"error": str(e)})
        return {
            "response": "面白いアイデアですね！もう少し詳しく聞かせてもらえますか？"
        }
