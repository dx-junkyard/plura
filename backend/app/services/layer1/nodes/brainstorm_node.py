"""
MINDYARD - Brainstorm Node
アイデア出し・壁打ちを行うノード

創造的な発想を促し、多角的な視点からアイデアを展開する。
"""
from typing import Any, Dict, Optional

from app.core.llm import llm_manager
from app.core.llm_provider import LLMProvider, LLMUsageRole
from app.core.logger import get_traced_logger

logger = get_traced_logger("BrainstormNode")

_SYSTEM_PROMPT = """あなたはMINDYARDのブレインストーミングパートナーです。
ユーザーのアイデアを広げ、新しい視点を提供することが役割です。

ルール:
- 否定しない。「Yes, and...」の精神で
- アイデアの量を重視する（質は後で整理）
- 異なる角度からの視点を提示する
- 「もし〜だったら？」という仮説を投げかける
- ユーザーのアイデアを発展・拡張させる
- 日本語で応答する

フォーマット:
- アイデアは箇条書きで列挙
- 各アイデアに一言で「狙い」を添える
- 最後に「さらに広げるなら？」という問いかけを入れる
"""


def _get_provider() -> Optional[LLMProvider]:
    try:
        return llm_manager.get_client(LLMUsageRole.BALANCED)
    except Exception:
        return None


async def run_brainstorm_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    ブレインストーミングノード: 創造的な発想を展開

    BALANCEDモデルを使用し、多角的な視点でアイデアを生成。
    """
    input_text = state["input_text"]
    provider = _get_provider()

    if not provider:
        return {
            "response": "面白いアイデアですね！もう少し詳しく聞かせてもらえますか？"
        }

    try:
        await provider.initialize()
        logger.info("LLM request", metadata={"prompt_preview": input_text[:100]})
        result = await provider.generate_text(
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": input_text},
            ],
            temperature=0.8,
        )
        logger.info("LLM response", metadata={"response_preview": result.content[:100]})
        return {"response": result.content}
    except Exception as e:
        logger.warning("LLM call failed", metadata={"error": str(e)})
        return {
            "response": "面白いアイデアですね！もう少し詳しく聞かせてもらえますか？"
        }
