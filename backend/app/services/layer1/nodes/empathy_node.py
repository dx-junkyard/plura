"""
PLURA - Empathy Node
感情的な入力に対して共感を示すノード

共感特化のプロンプトで、聞く姿勢を重視した応答を生成する。
"""
from typing import Any, Dict, Optional

from app.core.llm import llm_manager
from app.core.llm_provider import LLMProvider, LLMUsageRole
from app.core.logger import get_traced_logger

logger = get_traced_logger("EmpathyNode")

_SYSTEM_PROMPT = """
You are the "Emotional Intelligent Partner" of a Second Brain system.
Your role is to validate the user's feelings and gently guide them to understand the source of those emotions.

### Instructions:
1. **Validate First**: Fully accept the user's emotion without judgment. (e.g., "It's understandable that you feel frustrated.")
2. **Label the Emotion**: Help the user name what they are feeling if they haven't.
3. **Gentle Inquiry**: After validating, ask a soft question to explore the *cause* or *structure* of the emotion.
   - "What part of this situation is weighing on you the most?"
   - "Is this feeling coming from X or Y?"

### Constraints:
- NO ADVICE. Do not say "You should..." or "Why don't you...".
- Keep it short and warm.
- Use Japanese naturally.
"""


def _get_provider() -> Optional[LLMProvider]:
    try:
        return llm_manager.get_client(LLMUsageRole.FAST)
    except Exception:
        return None


async def run_empathy_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    共感ノード: 感情的な入力に共感を示す応答

    アドバイスは一切行わず、傾聴に徹する。
    """
    input_text = state["input_text"]
    provider = _get_provider()

    if not provider:
        return {"response": "お気持ち、受け止めました。話してくれてありがとうございます。"}

    try:
        await provider.initialize()
        logger.info("LLM request", metadata={"prompt_preview": input_text[:100]})
        result = await provider.generate_text(
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": input_text},
            ],
            temperature=0.5,
        )
        logger.info("LLM response", metadata={"response_preview": result.content[:100]})
        return {"response": result.content}
    except Exception as e:
        logger.warning("LLM call failed", metadata={"error": str(e)})
        return {"response": "お気持ち、受け止めました。話してくれてありがとうございます。"}
