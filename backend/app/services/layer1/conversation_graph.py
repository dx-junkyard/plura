"""
MINDYARD - Conversation Graph (LangGraph)
動的ルーティングによる会話グラフ

グラフ構造:
    Input → Router → [chat | empathy | knowledge | deep_dive | brainstorm] → END

Router はLLMでユーザー入力の意図を分類し、適切なNodeへルーティングする。
mode_override が指定されている場合、Routerの判定を上書きする（Mode Switcher機能）。
"""
import logging
from typing import Any, Dict, Optional

from langgraph.graph import StateGraph, END

from app.schemas.conversation import (
    ConversationIntent,
    ConversationResponse,
    IntentBadge,
    BackgroundTask,
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
    """会話グラフの共有ステート"""
    input_text: str
    intent: str
    confidence: float
    response: str
    user_id: str
    mode_override: Optional[str]
    background_task_info: Optional[Dict[str, Any]]


# --- Node Functions ---

async def router_node(state: AgentState) -> AgentState:
    """
    Intent Router Node: ユーザー入力を5カテゴリに分類

    mode_override が設定されている場合はLLM判定をスキップし、
    指定されたインテントを直接使用する（Mode Switcher機能）。
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

    # LLM による自動分類
    classification = await intent_router.classify(state["input_text"])
    return {
        "intent": classification["intent"].value,
        "confidence": classification["confidence"],
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


# --- 条件分岐関数 ---

def decide_next_node(state: AgentState) -> str:
    """Router の結果に基づいて次のノードを決定"""
    intent = state.get("intent", "chat")
    valid_intents = {"chat", "empathy", "knowledge", "deep_dive", "brainstorm"}
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
        },
    )

    # 終端エッジ: 各ノード → END
    workflow.add_edge("chat", END)
    workflow.add_edge("empathy", END)
    workflow.add_edge("knowledge", END)
    workflow.add_edge("deep_dive", END)
    workflow.add_edge("brainstorm", END)

    return workflow.compile()


# コンパイル済みグラフ（シングルトン）
app_graph = build_app_graph()


# --- 実行ヘルパー ---

async def run_conversation(
    input_text: str,
    user_id: str,
    mode_override: Optional[str] = None,
) -> ConversationResponse:
    """
    会話グラフを実行し、ConversationResponse を返す

    Args:
        input_text: ユーザー入力
        user_id: ユーザーID
        mode_override: モード強制上書き（Mode Switcher）

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
