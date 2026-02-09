"""
MINDYARD - Chit-Chat Node
雑談・カジュアルな会話を処理するノード

気軽で親しみやすいトーンで応答する。
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


def _get_provider() -> Optional[LLMProvider]:
    try:
        return llm_manager.get_client(LLMUsageRole.FAST)
    except Exception:
        return None


async def run_chat_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    雑談ノード: カジュアルな会話に応答

    LLMが利用できない場合はフォールバック応答を返す。
    """
    input_text = state["input_text"]
    provider = _get_provider()

    if not provider:
        return {"response": "なるほど！いいですね。"}

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
        logger.info("LLM response", metadata={"response_preview": result.content[:100]})
        return {"response": result.content}
    except Exception as e:
        logger.warning("LLM call failed", metadata={"error": str(e)})
        return {"response": "なるほど！いいですね。"}
