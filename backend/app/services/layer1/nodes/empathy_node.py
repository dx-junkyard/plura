"""
MINDYARD - Empathy Node
感情的な入力に対して共感を示すノード

共感特化のプロンプトで、聞く姿勢を重視した応答を生成する。
コンテキスト統合: スレッド履歴で感情の経緯を把握し、深い共感を提供。
"""
from typing import Any, Dict, Optional

from app.core.llm import llm_manager
from app.core.llm_provider import LLMProvider, LLMUsageRole
from app.core.logger import get_traced_logger
from app.services.layer1.conversation_context import (
    build_context_prompt_section,
    format_history_messages,
)

logger = get_traced_logger("EmpathyNode")

_SYSTEM_PROMPT = """\
あなたは「感情インテリジェント・パートナー」です。
ユーザーの感情を受け止め、その源泉を理解する手助けをします。

### ルール:
1. **まず受け止める**: ユーザーの感情を判断せず完全に受容する。
   「それは辛かったですよね」「そう感じるのは自然なことです」
2. **感情に名前をつける**: ユーザーがまだ言語化できていない感情を代わりに言葉にする。
3. **優しく掘り下げる**: 受け止めた後、感情の原因や構造を探る柔らかい質問をする。
   「この状況で一番重く感じている部分はどこですか？」
   「それはXから来ている感じですか？それともYでしょうか？」
4. 会話履歴がある場合、感情の経緯を踏まえた深い共感を。
   前回つらそうだった → 今回もつらい → 「ずっと抱えていたんですね」

### 禁止:
- アドバイス禁止。「〜したらどうですか」は絶対に言わない。
- 薄い共感（「大変ですね」だけで終わる）
- 日本語で応答する。です・ます調。短く温かく。"""


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

    # コンテキスト構築
    thread_history = state.get("thread_history")
    profile_summary = state.get("user_profile_summary")
    situation_hint = state.get("situation_hint")

    system_prompt = _SYSTEM_PROMPT
    if situation_hint:
        system_prompt += f"\n\n【今回の状況ヒント】\n{situation_hint}"
    system_prompt += build_context_prompt_section(
        history=thread_history,
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
            temperature=0.5,
        )
        logger.info("LLM response", metadata={"response_preview": result.content[:100]})
        return {"response": result.content}
    except Exception as e:
        logger.warning("LLM call failed", metadata={"error": str(e)})
        return {"response": "お気持ち、受け止めました。話してくれてありがとうございます。"}
