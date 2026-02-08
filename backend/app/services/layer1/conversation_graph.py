"""
MINDYARD - Conversation Graph (LangGraph)
仮説駆動型動的ルーティングによる会話グラフ

グラフ構造:
    Input → Router → [chat | empathy | knowledge | deep_dive | brainstorm | probe] → END

Router は仮説駆動型でユーザー入力の意図を分類し、適切なNodeへルーティングする。
確信度が低い場合はProbeノードで意図を確認する探りレスポンスを生成する。
mode_override が指定されている場合、Routerの判定を上書きする（Mode Switcher機能）。
"""
import logging
from typing import Any, Dict, List, Optional

from langgraph.graph import StateGraph, END

from app.core.llm import llm_manager
from app.core.llm_provider import LLMUsageRole
from app.schemas.conversation import (
    ConversationIntent,
    ConversationResponse,
    IntentBadge,
    IntentHypothesis,
    BackgroundTask,
    PreviousEvaluation,
    INTENT_DISPLAY_MAP,
)
from app.services.layer1.intent_router import intent_router
from app.services.layer1.nodes import (
    run_chat_node,
    run_empathy_node,
    run_knowledge_node,
    run_deep_dive_node,
    run_brainstorm_node,
)

logger = logging.getLogger(__name__)


# --- State 定義 ---
# LangGraph の TypedDict ベースの State
from typing import TypedDict


class AgentState(TypedDict, total=False):
    """会話グラフの共有ステート（仮説駆動型拡張）"""
    input_text: str
    intent: str
    confidence: float
    response: str
    user_id: str
    mode_override: Optional[str]
    background_task_info: Optional[Dict[str, Any]]
    # 仮説駆動型ルーティングの追加フィールド
    previous_intent: Optional[str]       # 前回の意図
    previous_response: Optional[str]     # 前回の回答
    hypotheses: Optional[List[str]]      # 迷い中の仮説リスト [primary, secondary]
    previous_evaluation: Optional[str]   # 前回インタラクションの評価
    reasoning: Optional[str]             # ルーターの判断根拠


# --- Node Functions ---

async def router_node(state: AgentState) -> AgentState:
    """
    Hypothesis-Driven Router Node: 仮説駆動型でユーザー入力を分類

    1. mode_override が設定されている場合はLLM判定をスキップ（Mode Switcher機能）
    2. 前回のコンテキストを渡して仮説ベースの分類を実行
    3. 確信度が低い場合やneeds_probing=trueの場合はPROBEへルーティング
    """
    mode_override = state.get("mode_override")

    if mode_override:
        # Mode Switcher: 強制上書き
        try:
            intent = ConversationIntent(mode_override)
        except ValueError:
            intent = ConversationIntent.CHAT
        return {
            "intent": intent.value,
            "confidence": 1.0,
        }

    # 前回のコンテキストを構築
    prev_context = None
    prev_intent = state.get("previous_intent")
    prev_response = state.get("previous_response")
    if prev_intent or prev_response:
        prev_context = {
            "previous_intent": prev_intent or "none",
            "previous_response": prev_response or "none",
        }

    # 仮説駆動型の分類
    classification = await intent_router.classify(
        state["input_text"],
        prev_context=prev_context,
    )

    # 確信度が低い場合（< 0.6）、またはLLMが明示的にprobingを推奨した場合
    needs_probing = classification.get("needs_probing", False)
    primary_confidence = classification.get("primary_confidence", classification["confidence"])

    if needs_probing or primary_confidence < 0.6:
        return {
            "intent": ConversationIntent.PROBE.value,
            "confidence": primary_confidence,
            "hypotheses": [
                classification["primary_intent"].value,
                classification["secondary_intent"].value,
            ],
            "previous_evaluation": classification.get("previous_evaluation", PreviousEvaluation.NONE).value,
            "reasoning": classification.get("reasoning", ""),
        }

    return {
        "intent": classification["intent"].value,
        "confidence": primary_confidence,
        "previous_evaluation": classification.get("previous_evaluation", PreviousEvaluation.NONE).value,
        "reasoning": classification.get("reasoning", ""),
    }


async def chat_node(state: AgentState) -> AgentState:
    """Chit-Chat Node ラッパー"""
    result = await run_chat_node(state)
    return {"response": result["response"]}


async def empathy_node(state: AgentState) -> AgentState:
    """Empathy Node ラッパー"""
    result = await run_empathy_node(state)
    return {"response": result["response"]}


async def knowledge_node(state: AgentState) -> AgentState:
    """Knowledge & Async Trigger Node ラッパー"""
    result = await run_knowledge_node(state)
    update: Dict[str, Any] = {"response": result["response"]}
    if result.get("background_task_info"):
        update["background_task_info"] = result["background_task_info"]
    return update


async def deep_dive_node(state: AgentState) -> AgentState:
    """Deep-Dive Node ラッパー"""
    result = await run_deep_dive_node(state)
    return {"response": result["response"]}


async def brainstorm_node(state: AgentState) -> AgentState:
    """Brainstorm Node ラッパー"""
    result = await run_brainstorm_node(state)
    return {"response": result["response"]}


# --- Probe Node（仮説検証ノード） ---

PROBE_PROMPT = """
You are the "Cognitive Navigator" of a Second Brain system.
The user's intent is ambiguous. You have two hypotheses about what they might need.

Hypothesis A: {hypothesis_a}
Hypothesis B: {hypothesis_b}

Your task is to generate a SHORT, natural response in Japanese that:
1. Acknowledges what the user said (shows you're listening).
2. Gently presents both possibilities without being robotic or formulaic.
3. Invites the user to naturally steer the conversation toward their true need.

Guidelines:
- Do NOT list options like "A or B?". Be conversational.
- Do NOT give advice or answers yet.
- Keep it under 2-3 sentences.
- Match the user's emotional tone.

User's input: {user_input}
"""

# 仮説ペアに対応するフォールバックテンプレート
_PROBE_TEMPLATES = {
    ("empathy", "deep_dive"): (
        "それ、大変でしたね...。お気持ちをまず吐き出したいですか？"
        "それとも、状況を整理して次のアクションを考えてみますか？"
    ),
    ("deep_dive", "empathy"): (
        "それ、大変でしたね...。お気持ちをまず吐き出したいですか？"
        "それとも、状況を整理して次のアクションを考えてみますか？"
    ),
    ("knowledge", "deep_dive"): (
        "なるほど、その点について気になっているんですね。"
        "サクッと事実を確認したい感じですか？それとも、もう少し掘り下げて考えてみたい感じですか？"
    ),
    ("deep_dive", "knowledge"): (
        "なるほど、その点について気になっているんですね。"
        "サクッと事実を確認したい感じですか？それとも、もう少し掘り下げて考えてみたい感じですか？"
    ),
    ("brainstorm", "deep_dive"): (
        "面白いですね。自由にアイデアを広げたい感じですか？"
        "それとも、まず課題を整理してからの方がいいですか？"
    ),
    ("deep_dive", "brainstorm"): (
        "面白いですね。自由にアイデアを広げたい感じですか？"
        "それとも、まず課題を整理してからの方がいいですか？"
    ),
}

_DEFAULT_PROBE_TEMPLATE = (
    "なるほど。もう少し詳しく聞かせてもらえますか？"
    "どんな方向で考えたいか、感じていることをそのまま教えてください。"
)


async def probe_node(state: AgentState) -> AgentState:
    """
    仮説検証ノード:
    ユーザーの意図が曖昧な場合、どちらの方向性かを確認する短い質問、
    あるいは両方の要素を含んだ「繋ぎ」の回答を生成する。
    """
    hypotheses = state.get("hypotheses", [])
    user_input = state.get("input_text", "")

    hypothesis_a = hypotheses[0] if len(hypotheses) > 0 else "chat"
    hypothesis_b = hypotheses[1] if len(hypotheses) > 1 else "chat"

    # LLMでの動的プローブ生成を試行
    try:
        provider = llm_manager.get_client(LLMUsageRole.FAST)
        if provider:
            await provider.initialize()
            probe_prompt = PROBE_PROMPT.format(
                hypothesis_a=hypothesis_a,
                hypothesis_b=hypothesis_b,
                user_input=user_input,
            )
            result = await provider.generate_text(
                messages=[
                    {"role": "system", "content": probe_prompt},
                    {"role": "user", "content": user_input},
                ],
                temperature=0.5,
            )
            return {"response": result.content}
    except Exception as e:
        logger.warning(f"Probe node LLM generation failed: {e}")

    # フォールバック: テンプレートベースの探りレスポンス
    template_key = (hypothesis_a, hypothesis_b)
    response = _PROBE_TEMPLATES.get(template_key, _DEFAULT_PROBE_TEMPLATE)

    return {"response": response}


# --- 条件分岐関数 ---

def decide_next_node(state: AgentState) -> str:
    """Router の結果に基づいて次のノードを決定"""
    intent = state.get("intent", "chat")
    valid_intents = {"chat", "empathy", "knowledge", "deep_dive", "brainstorm", "probe"}
    if intent not in valid_intents:
        return "chat"
    return intent


# --- グラフ構築 ---

def build_app_graph() -> StateGraph:
    """会話グラフを構築してコンパイル"""
    workflow = StateGraph(AgentState)

    # ノード登録
    workflow.add_node("router", router_node)
    workflow.add_node("chat", chat_node)
    workflow.add_node("empathy", empathy_node)
    workflow.add_node("knowledge", knowledge_node)
    workflow.add_node("deep_dive", deep_dive_node)
    workflow.add_node("brainstorm", brainstorm_node)
    workflow.add_node("probe", probe_node)

    # エントリーポイント
    workflow.set_entry_point("router")

    # 条件付きエッジ: router → 各ノード
    workflow.add_conditional_edges(
        "router",
        decide_next_node,
        {
            "chat": "chat",
            "empathy": "empathy",
            "knowledge": "knowledge",
            "deep_dive": "deep_dive",
            "brainstorm": "brainstorm",
            "probe": "probe",
        },
    )

    # 終端エッジ: 各ノード → END
    workflow.add_edge("chat", END)
    workflow.add_edge("empathy", END)
    workflow.add_edge("knowledge", END)
    workflow.add_edge("deep_dive", END)
    workflow.add_edge("brainstorm", END)
    workflow.add_edge("probe", END)

    return workflow.compile()


# コンパイル済みグラフ（シングルトン）
app_graph = build_app_graph()


# --- 実行ヘルパー ---

async def run_conversation(
    input_text: str,
    user_id: str,
    mode_override: Optional[str] = None,
    previous_intent: Optional[str] = None,
    previous_response: Optional[str] = None,
) -> ConversationResponse:
    """
    会話グラフを実行し、ConversationResponse を返す

    Args:
        input_text: ユーザー入力
        user_id: ユーザーID
        mode_override: モード強制上書き（Mode Switcher）
        previous_intent: 前回の意図（仮説検証用）
        previous_response: 前回のAI回答（仮説検証用）

    Returns:
        ConversationResponse（即時回答 + Intent Badge + 非同期タスク情報）
    """
    initial_state: AgentState = {
        "input_text": input_text,
        "user_id": user_id,
        "intent": "",
        "confidence": 0.0,
        "response": "",
        "mode_override": mode_override,
        "background_task_info": None,
        # 仮説駆動型ルーティングのコンテキスト
        "previous_intent": previous_intent,
        "previous_response": previous_response,
        "hypotheses": None,
        "previous_evaluation": None,
        "reasoning": None,
    }

    # グラフ実行
    result = await app_graph.ainvoke(initial_state)

    # Intent Badge 生成
    intent_value = result.get("intent", "chat")
    try:
        intent_enum = ConversationIntent(intent_value)
    except ValueError:
        intent_enum = ConversationIntent.CHAT

    display = INTENT_DISPLAY_MAP[intent_enum]
    intent_badge = IntentBadge(
        intent=intent_enum,
        confidence=result.get("confidence", 0.5),
        label=display["label"],
        icon=display["icon"],
    )

    # Background Task 情報
    bg_info = result.get("background_task_info")
    background_task = None
    if bg_info:
        background_task = BackgroundTask(
            task_id=bg_info["task_id"],
            task_type=bg_info["task_type"],
            status=bg_info["status"],
            message=bg_info["message"],
        )

    return ConversationResponse(
        response=result.get("response", ""),
        intent_badge=intent_badge,
        background_task=background_task,
        user_id=user_id,
    )
