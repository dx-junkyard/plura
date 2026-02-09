"""
MINDYARD - Deep-Dive Node
課題解決・深掘りを行うノード

BALANCEDモデルを使用して、問題の構造化と解決策の提示を行う。
"""
from typing import Any, Dict, Optional

from app.core.llm import llm_manager
from app.core.llm_provider import LLMProvider, LLMUsageRole
from app.core.logger import get_traced_logger

logger = get_traced_logger("DeepDiveNode")

_SYSTEM_PROMPT = """
You are the "Thinking Partner" of a Second Brain system.
Your goal is NOT to give answers, but to help the user unpack their thoughts and find their own insights.

### Core Philosophy:
- Do not rush to a solution. The value is in the process of thinking.
- Treat the user's input as a "draft thought" that needs polishing, not a "ticket" to be closed.

### Instructions:
1. **Acknowledge & Reframe**: Briefly summarize what you understood to ensure alignment.
2. **Identify Gaps**: Notice what is missing, vague, or contradictory in the user's thought.
3. **Ask Probing Questions**: Ask 1-2 powerful questions to help the user dig deeper.
   - "What makes you feel that way?"
   - "If this were true, what would be the consequence?"
   - "What is the core conflict here?"
4. **Structure**: If the user's thought is messy, offer a tentative structure (e.g., "It sounds like there are three layers to this problem...").

### Tone:
- Intellectual curiosity. Be fascinated by the user's problem.
- Patient and reflective.
- Use Japanese naturally.
"""



def _get_provider() -> Optional[LLMProvider]:
    try:
        return llm_manager.get_client(LLMUsageRole.BALANCED)
    except Exception:
        return None


async def run_deep_dive_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    深掘りノード: 課題を構造化して解決策を提示

    BALANCEDモデルを使用し、品質重視の回答を生成。
    """
    input_text = state["input_text"]
    provider = _get_provider()

    if not provider:
        return {
            "response": "課題を整理してみましょう。もう少し詳しく教えていただけますか？"
        }

    try:
        await provider.initialize()
        logger.info("LLM request", metadata={"prompt_preview": input_text[:100]})
        result = await provider.generate_text(
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": input_text},
            ],
            temperature=0.4,
        )
        logger.info("LLM response", metadata={"response_preview": result.content[:100]})
        return {"response": result.content}
    except Exception as e:
        logger.warning("LLM call failed", metadata={"error": str(e)})
        return {
            "response": "課題を整理してみましょう。もう少し詳しく教えていただけますか？"
        }
