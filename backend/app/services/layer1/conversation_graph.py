"""
MINDYARD - Conversation Graph (LangGraph)
仮説駆動型動的ルーティングによる会話グラフ

グラフ構造:
    Input → Router → [chat | empathy | knowledge | deep_dive | brainstorm | probe] → END

Router は仮説駆動型でユーザー入力の意図を分類し、適切なNodeへルーティングする。
確信度が低い場合はProbeノードで意図を確認する探りレスポンスを生成する。
mode_override が指定されている場合、Routerの判定を上書きする（Mode Switcher機能）。
"""
import time
from typing import Any, Dict, List, Optional

from langgraph.graph import StateGraph, END

from app.core.llm import llm_manager
from app.core.llm_provider import LLMUsageRole
from app.core.logger import get_traced_logger
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
    run_state_node,
)

logger = get_traced_logger("Graph")


# --- State 定義 ---
# LangGraph の TypedDict ベースの State
from typing import TypedDict


class AgentState(TypedDict, total=False):
    """会話グラフの共有ステート（仮説駆動型拡張 + コンテキスト統合）"""
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
    alternative_intent: Optional[str]    # 僅差だった場合の第2候補（補足ヒント用）
    # ── コンテキスト統合フィールド（/logs/ 統合用） ──
    thread_history: Optional[List[tuple]]        # [(user_content, assistant_reply), ...]
    collective_wisdom: Optional[List[Dict[str, Any]]]  # Qdrant 検索結果
    user_profile_summary: Optional[str]          # ユーザープロファイル要約
    situation_hint: Optional[str]                # SituationRouter のヒント文


# --- Node Functions ---

async def router_node(state: AgentState) -> AgentState:
    """
    Hypothesis-Driven Router Node (Action with Fallback Option)

    判定ロジック:
    1. mode_override → 強制上書き（Mode Switcher機能）
    2. primary_confidence < 0.3 → Probe（本当に自信がない場合のみ聞き返す）
    3. primary - secondary < 0.1 → 1位を採用しつつ alternative_intent を設定
       → 各Nodeが回答末尾に「もし〇〇のつもりなら〜」の補足を付与
    4. それ以外 → 1位をそのまま採用
    """
    mode_override = state.get("mode_override")

    if mode_override:
        # Mode Switcher: 強制上書き
        try:
            intent = ConversationIntent(mode_override)
        except ValueError:
            intent = ConversationIntent.CHAT
        logger.info(
            "Router: mode_override applied",
            metadata={"intent": intent.value},
        )
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

    primary_conf = classification.get("primary_confidence", classification["confidence"])
    secondary_conf = classification.get("secondary_confidence", 0.0)
    primary_intent = classification["primary_intent"]
    secondary_intent = classification["secondary_intent"]
    prev_eval = classification.get("previous_evaluation", PreviousEvaluation.NONE)
    reasoning = classification.get("reasoning", "")

    # 1. 本当に自信がない場合のみProbe
    if primary_conf < 0.3:
        logger.info(
            "Router: low confidence, routing to Probe",
            metadata={
                "primary_intent": primary_intent.value,
                "primary_confidence": primary_conf,
                "secondary_intent": secondary_intent.value,
            },
        )
        return {
            "intent": ConversationIntent.PROBE.value,
            "confidence": primary_conf,
            "hypotheses": [primary_intent.value, secondary_intent.value],
            "previous_evaluation": prev_eval.value,
            "reasoning": reasoning,
        }

    # 2. 僅差の場合: 1位を採用しつつ、2位を代替案として保持
    alternative_intent = None
    if (primary_conf - secondary_conf) < 0.1 and secondary_conf > 0.1:
        alternative_intent = secondary_intent.value

    logger.info(
        "Router: intent determined",
        metadata={
            "intent": primary_intent.value,
            "confidence": primary_conf,
            "alternative_intent": alternative_intent,
        },
    )

    return {
        "intent": primary_intent.value,
        "confidence": primary_conf,
        "alternative_intent": alternative_intent,
        "previous_evaluation": prev_eval.value,
        "reasoning": reasoning,
    }


# --- Fallback Hint（代替案の補足メッセージ） ---

# alternative_intent に対応する補足ヒントのマッピング
# 「もし〇〇のつもりだったら、こう言ってね」を自然な日本語で表現
_ALTERNATIVE_HINTS = {
    "chat": "気軽に雑談したい場合は、そのままお話しくださいね。",
    "empathy": "もしお気持ちを吐き出したい場合は、遠慮なくおっしゃってくださいね。",
    "knowledge": "もし事実やデータをサクッと確認したい場合は、そのようにお伝えください。",
    "deep_dive": "もし具体的な課題の整理や解決策の相談をしたい場合は、そのようにおっしゃってくださいね。",
    "brainstorm": "もしこれを起点にアイデアを広げたい場合は、一緒にブレストしましょう。",
    "state_share": "体調やコンディションを記録したい場合は、そのままお伝えくださいね。",
}


def _append_fallback_hint(response: str, alternative_intent: Optional[str]) -> str:
    """alternative_intent がある場合、回答末尾に補足ヒントを付加する"""
    if not alternative_intent:
        return response
    hint = _ALTERNATIVE_HINTS.get(alternative_intent)
    if not hint:
        return response
    return f"{response}\n\n{hint}"


# --- Node Wrappers ---

_node_logger = get_traced_logger("Node")


async def _traced_node_wrapper(
    node_name: str,
    node_fn,
    state: AgentState,
) -> Dict[str, Any]:
    """各ノードの実行をトレース付きで行う共通ラッパー"""
    _node_logger.info(
        f"{node_name} started",
        metadata={"input_preview": state.get("input_text", "")[:80]},
    )
    start = time.monotonic()
    result = await node_fn(state)
    duration_ms = round((time.monotonic() - start) * 1000, 1)
    _node_logger.info(
        f"{node_name} completed",
        metadata={
            "duration_ms": duration_ms,
            "response_preview": result.get("response", "")[:100],
        },
    )
    return result


async def chat_node(state: AgentState) -> AgentState:
    """Chit-Chat Node ラッパー"""
    result = await _traced_node_wrapper("ChatNode", run_chat_node, state)
    response = _append_fallback_hint(result["response"], state.get("alternative_intent"))
    return {"response": response}


async def empathy_node(state: AgentState) -> AgentState:
    """Empathy Node ラッパー"""
    result = await _traced_node_wrapper("EmpathyNode", run_empathy_node, state)
    response = _append_fallback_hint(result["response"], state.get("alternative_intent"))
    return {"response": response}


async def knowledge_node(state: AgentState) -> AgentState:
    """Knowledge & Async Trigger Node ラッパー"""
    result = await _traced_node_wrapper("KnowledgeNode", run_knowledge_node, state)
    response = _append_fallback_hint(result["response"], state.get("alternative_intent"))
    update: Dict[str, Any] = {"response": response}
    if result.get("background_task_info"):
        update["background_task_info"] = result["background_task_info"]
    return update


async def deep_dive_node(state: AgentState) -> AgentState:
    """Deep-Dive Node ラッパー"""
    result = await _traced_node_wrapper("DeepDiveNode", run_deep_dive_node, state)
    response = _append_fallback_hint(result["response"], state.get("alternative_intent"))
    return {"response": response}


async def brainstorm_node(state: AgentState) -> AgentState:
    """Brainstorm Node ラッパー"""
    result = await _traced_node_wrapper("BrainstormNode", run_brainstorm_node, state)
    response = _append_fallback_hint(result["response"], state.get("alternative_intent"))
    return {"response": response}


async def state_share_node(state: AgentState) -> AgentState:
    """State Share Node ラッパー（コンディション記録）"""
    result = await _traced_node_wrapper("StateNode", run_state_node, state)
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

    _node_logger.info(
        "ProbeNode started",
        metadata={
            "hypothesis_a": hypothesis_a,
            "hypothesis_b": hypothesis_b,
            "input_preview": user_input[:80],
        },
    )
    start = time.monotonic()

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
            duration_ms = round((time.monotonic() - start) * 1000, 1)
            _node_logger.info(
                "ProbeNode completed (LLM)",
                metadata={
                    "duration_ms": duration_ms,
                    "response_preview": result.content[:100],
                },
            )
            return {"response": result.content}
    except Exception as e:
        _node_logger.warning(
            "ProbeNode LLM failed, using template fallback",
            metadata={"error": str(e)},
        )

    # フォールバック: テンプレートベースの探りレスポンス
    template_key = (hypothesis_a, hypothesis_b)
    response = _PROBE_TEMPLATES.get(template_key, _DEFAULT_PROBE_TEMPLATE)

    duration_ms = round((time.monotonic() - start) * 1000, 1)
    _node_logger.info(
        "ProbeNode completed (template fallback)",
        metadata={"duration_ms": duration_ms},
    )

    return {"response": response}


# --- 条件分岐関数 ---

def decide_next_node(state: AgentState) -> str:
    """Router の結果に基づいて次のノードを決定"""
    intent = state.get("intent", "chat")
    valid_intents = {"chat", "empathy", "knowledge", "deep_dive", "brainstorm", "probe", "state_share"}
    if intent not in valid_intents:
        logger.warning(
            "Transitioning to fallback node",
            metadata={"invalid_intent": intent, "fallback": "chat"},
        )
        return "chat"
    logger.info(f"Transitioning to {intent} node")
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
    workflow.add_node("state_share", state_share_node)
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
            "state_share": "state_share",
            "probe": "probe",
        },
    )

    # 終端エッジ: 各ノード → END
    workflow.add_edge("chat", END)
    workflow.add_edge("empathy", END)
    workflow.add_edge("knowledge", END)
    workflow.add_edge("deep_dive", END)
    workflow.add_edge("brainstorm", END)
    workflow.add_edge("state_share", END)
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
    # ── コンテキスト統合（/logs/ 統合用） ──
    thread_history: Optional[List[tuple]] = None,
    collective_wisdom: Optional[List[Dict[str, Any]]] = None,
    user_profile_summary: Optional[str] = None,
    situation_hint: Optional[str] = None,
) -> ConversationResponse:
    """
    会話グラフを実行し、ConversationResponse を返す

    Args:
        input_text: ユーザー入力
        user_id: ユーザーID
        mode_override: モード強制上書き（Mode Switcher）
        previous_intent: 前回の意図（仮説検証用）
        previous_response: 前回のAI回答（仮説検証用）
        thread_history: スレッド内の会話履歴 [(user_content, assistant_reply), ...]
        collective_wisdom: Qdrant から取得した関連インサイト
        user_profile_summary: ユーザープロファイル要約テキスト
        situation_hint: SituationRouter による状況ヒント文

    Returns:
        ConversationResponse（即時回答 + Intent Badge + 非同期タスク情報）
    """
    logger.info(
        "run_conversation started",
        metadata={
            "input_preview": input_text[:80],
            "user_id": user_id,
            "mode_override": mode_override,
            "has_thread_history": thread_history is not None and len(thread_history or []) > 0,
            "has_collective_wisdom": collective_wisdom is not None and len(collective_wisdom or []) > 0,
            "has_profile": user_profile_summary is not None,
        },
    )
    conv_start = time.monotonic()

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
        "alternative_intent": None,
        # コンテキスト統合
        "thread_history": thread_history,
        "collective_wisdom": collective_wisdom,
        "user_profile_summary": user_profile_summary,
        "situation_hint": situation_hint,
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

    conv_response = ConversationResponse(
        response=result.get("response", ""),
        intent_badge=intent_badge,
        background_task=background_task,
        user_id=user_id,
    )

    duration_ms = round((time.monotonic() - conv_start) * 1000, 1)
    logger.info(
        "run_conversation completed",
        metadata={
            "intent": intent_enum.value,
            "confidence": intent_badge.confidence,
            "has_background_task": background_task is not None,
            "duration_ms": duration_ms,
        },
    )

    return conv_response
