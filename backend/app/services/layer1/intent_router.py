"""
PLURA - Intent Router (Hypothesis-Driven)
仮説駆動型ルーティング: ユーザーの真意を仮説→検証→修正のループで推定する

分類カテゴリ:
- chat: 雑談・カジュアル
- empathy: 感情的・共感要求
- knowledge: 知識要求・質問
- deep_dive: 課題解決・深掘り
- brainstorm: 発想・アイデア出し
- probe: 意図確認（確信度が低い場合の探り）

Semantic Router:
- 短い入力（50文字以下）に対してEmbeddingベースの軽量分類を行う
- LLMの深読みによるEmpathy誤爆を防止する
"""
import math
from typing import Any, Dict, List, Optional

from app.core.llm import llm_manager
from app.core.llm_provider import LLMProvider, LLMUsageRole
from app.core.logger import get_traced_logger
from app.schemas.conversation import ConversationIntent, PreviousEvaluation

logger = get_traced_logger("Router")

ROUTER_PROMPT = """
You are the "Cognitive Navigator" of a Second Brain system.
Your goal is to infer the user's *true intent* by forming and testing hypotheses.

Input Context:
- Current Input: The user's latest message.
- Previous Intent: The intent we acted upon in the last turn.
- Previous System Response: What we said last time.

### Task 1: Evaluate Previous Interaction (Implicit Feedback)
Did the user's current input suggest they were satisfied with the Previous Intent?
- **positive**: They continued the topic, said thanks, or went deeper.
- **negative**: They ignored our answer, restated their question, or changed tone abruptly.
- **pivot**: They acknowledged it but explicitly moved to a new topic.
- **none**: No previous context available (first turn).

### Task 2: Formulate Hypotheses for Current Input
Based on the evaluation and current input, generate the top 2 likely intents.

Available Intents:
- `chat`: Casual, greeting.
- `state_share`: User is reporting their current condition or a brief observation. This includes:
  - Physical state: tired, sleepy, hungry, hot, cold
  - Positive mood/observation: "nice weather!", "feeling great", "done for the day"
  - Neutral status updates: short messages (1-5 words), NOT asking for help or analysis.
  NOTE: Positive emotions ("嬉しい", "いい天気", "気持ちいい") are state_share, NOT empathy.
- `empathy`: User is venting **negative** emotions (anger, frustration, sadness, anxiety) about a specific event or situation, and seeks emotional support. Longer than a state share, with context. Does NOT include positive feelings.
- `knowledge`: Factual questions, "how-to".
- `deep_dive`: Complex problem solving, analysis, structural thinking.
- `brainstorm`: Idea generation, "what if".
- `summarize`: User wants to summarize or get an overview of uploaded documents. Keywords: 要約, まとめ, サマリー, 概要, ざっくり教えて.

### Task 3: Decision
- If Confidence is high (> 0.8), select the `primary_intent`.
- If Confidence is low or ambiguous (e.g., between empathy and deep_dive), set `needs_probing` to true.
  - A probe means we need to ask a clarifying question or give a hybrid response to see how the user reacts.

### Constraint:
- If the message is very short (1-5 words) and expresses a physical/mental state without asking anything, choose `state_share`.
- If you are unsure between `chat` and `deep_dive`, lean toward `deep_dive`.
- Always respond in the following JSON format:
{
    "previous_evaluation": "positive" | "negative" | "pivot" | "none",
    "primary_intent": "intent_name",
    "primary_confidence": 0.0 to 1.0,
    "secondary_intent": "intent_name",
    "secondary_confidence": 0.0 to 1.0,
    "needs_probing": true | false,
    "reasoning": "Short explanation of why we think this."
}
"""


# ルールベース判定のキーワードマッピング
_KEYWORD_MAP = {
    ConversationIntent.STATE_SHARE: [
        # ネガティブ状態
        "眠い", "眠たい", "だるい", "疲れた", "お腹すいた", "腹減った",
        "暑い", "寒い", "頭痛い", "しんど", "ねむ", "つかれ",
        "終わったー", "帰りたい", "やばい", "無理", "限界",
        # ポジティブ状態・観察
        "いい天気", "天気", "気持ちいい", "気分が良い", "気分いい",
        "嬉しい", "楽しい", "最高", "いい感じ", "スッキリ",
        "できた", "終わった", "頑張った",
    ],
    ConversationIntent.EMPATHY: [
        "つらい", "しんどい", "嫌だ", "ひどい", "悲しい",
        "不安", "怖い", "寂しい", "イライラ", "ムカつく", "最悪",
        "聞いて", "吐き出し", "愚痴", "ため息",
    ],
    ConversationIntent.KNOWLEDGE: [
        "教えて", "知りたい", "とは", "って何", "ですか",
        "違いは", "方法は", "やり方", "調べ", "検索",
        "参考", "文献", "論文", "データ",
    ],
    ConversationIntent.DEEP_DIVE: [
        "どうすれば", "解決", "改善", "対策", "問題",
        "原因", "なぜ", "課題", "困って", "うまくいかない",
        "分析", "検討", "整理したい", "深掘り",
    ],
    ConversationIntent.BRAINSTORM: [
        "アイデア", "案", "ひらめき", "思いつき", "仮説",
        "壁打ち", "ブレスト", "発想", "もし", "可能性",
        "新しい", "試したい", "どうだろう", "妄想",
    ],
}


class SemanticRouter:
    """
    Embeddingベースの軽量意図分類器 (Semantic Router)

    短い入力（50文字以下）に対してLLMを呼ばずに、
    事前定義したアンカーテキスト群とのコサイン類似度で即座にIntentを決定する。

    目的:
    - 「要約して」「教えて」のような短い指示文に対し、
      LLMが過剰解釈してEmpathyモードに誤爆するのを防ぐ。
    - アンカーEmbeddingはインスタンスにキャッシュし、初回のみ計算する。
    """

    # 各Intentの代表的なアンカーテキスト
    _INTENT_ANCHORS: Dict[str, List[str]] = {
        "summarize": [
            "要約して", "まとめて", "要点を教えて", "サマリーを教えて",
            "概要を教えて", "論文を要約して", "内容をまとめて",
            "要約をおしえてほしい", "内容を教えて", "まとめてほしい",
            "要約お願い", "サマリー", "要点は？", "ざっくり教えて",
        ],
        "deep_dive": [
            "詳しく教えて", "分析して", "解説して", "教えて",
            "について教えて", "詳細を教えて", "これについて教えて",
            "詳しく説明して", "解析して", "調べて",
        ],
        "knowledge": [
            "とは何ですか", "何ですか", "どういう意味", "意味は",
            "教えてください", "知りたい", "とは", "って何",
        ],
        "empathy": [
            "疲れた", "つらい", "しんどい", "もう無理", "悲しい",
            "不安です", "怖い", "寂しい", "ストレス溜まる", "辛い",
            "しんどいです", "消えたい", "もうダメ",
        ],
        "state_share": [
            "眠い", "お腹すいた", "暑い", "寒い", "いい天気",
            "気分がいい", "頭痛い", "体調悪い", "疲れた", "眠たい",
        ],
        "chat": [
            "おはよう", "こんにちは", "ありがとう", "よろしく",
            "おやすみ", "はじめまして", "やあ", "ねえ",
        ],
    }

    # Semantic intent → ConversationIntent のマッピング
    _TO_CONVERSATION_INTENT: Dict[str, ConversationIntent] = {
        "summarize": ConversationIntent.SUMMARIZE,
        "deep_dive": ConversationIntent.DEEP_DIVE,
        "knowledge": ConversationIntent.KNOWLEDGE,
        "empathy": ConversationIntent.EMPATHY,
        "state_share": ConversationIntent.STATE_SHARE,
        "chat": ConversationIntent.CHAT,
    }

    # この閾値以上のコサイン類似度があれば確信とみなす
    _SIMILARITY_THRESHOLD = 0.45

    # 短い入力の最大文字数
    SHORT_INPUT_MAX_LEN = 50

    def __init__(self) -> None:
        # アンカーEmbeddingのキャッシュ: {intent_name: List[List[float]]}
        self._anchor_embeddings: Optional[Dict[str, List[List[float]]]] = None

    async def _get_embedding_provider(self):
        """EmbeddingManagerからプロバイダーを取得"""
        try:
            from app.core.embedding import embedding_manager
            return embedding_manager.get_provider()
        except Exception:
            return None

    async def _ensure_anchor_embeddings(self) -> bool:
        """
        アンカーテキストのEmbeddingをキャッシュ（初回のみ計算）
        Returns: キャッシュ準備ができているか
        """
        if self._anchor_embeddings is not None:
            return True

        provider = await self._get_embedding_provider()
        if not provider:
            return False

        try:
            await provider.initialize()
            cache: Dict[str, List[List[float]]] = {}
            for intent_name, anchors in self._INTENT_ANCHORS.items():
                embeddings = await provider.embed_texts(anchors)
                if embeddings:
                    cache[intent_name] = embeddings
            self._anchor_embeddings = cache
            logger.info(
                "SemanticRouter: anchor embeddings cached",
                metadata={"intents": list(cache.keys())},
            )
            return True
        except Exception as e:
            logger.warning(
                "SemanticRouter: failed to cache anchor embeddings",
                metadata={"error": str(e)},
            )
            return False

    @staticmethod
    def _cosine_similarity(a: List[float], b: List[float]) -> float:
        """コサイン類似度を計算"""
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(y * y for y in b))
        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0
        return dot / (norm_a * norm_b)

    def _max_similarity_for_intent(
        self,
        input_emb: List[float],
        anchor_embs: List[List[float]],
    ) -> float:
        """入力EmbeddingとIntentのアンカー群の最大コサイン類似度を返す"""
        return max(
            self._cosine_similarity(input_emb, anchor)
            for anchor in anchor_embs
        )

    async def route(
        self,
        input_text: str,
    ) -> Optional[Dict[str, Any]]:
        """
        短い入力をEmbeddingベースで意図分類する。

        入力が SHORT_INPUT_MAX_LEN 文字を超える場合は None を返し、
        通常の LLM ルーティングに委ねる。

        Returns:
            {
                "intent": ConversationIntent,
                "semantic_intent": str,   # "summarize" | "deep_dive" | etc.
                "confidence": float,
                "method": "semantic_router",
            }
            または None（判定できない場合・入力が長い場合）
        """
        text = input_text.strip()
        if len(text) > self.SHORT_INPUT_MAX_LEN:
            return None

        provider = await self._get_embedding_provider()
        if not provider:
            return None

        if not await self._ensure_anchor_embeddings():
            return None

        try:
            await provider.initialize()
            input_emb = await provider.embed_text(text)
            if not input_emb:
                return None
        except Exception as e:
            logger.debug(
                "SemanticRouter: embed_text failed",
                metadata={"error": str(e)},
            )
            return None

        # 各Intentとのコサイン類似度を計算し、最大スコアのIntentを選ぶ
        best_intent: Optional[str] = None
        best_score = 0.0

        for intent_name, anchor_embs in self._anchor_embeddings.items():
            score = self._max_similarity_for_intent(input_emb, anchor_embs)
            if score > best_score:
                best_score = score
                best_intent = intent_name

        if best_intent is None or best_score < self._SIMILARITY_THRESHOLD:
            logger.debug(
                "SemanticRouter: no confident match",
                metadata={"best_intent": best_intent, "best_score": best_score},
            )
            return None

        conversation_intent = self._TO_CONVERSATION_INTENT.get(
            best_intent, ConversationIntent.CHAT
        )

        logger.info(
            "SemanticRouter: routed",
            metadata={
                "input_preview": text[:40],
                "semantic_intent": best_intent,
                "conversation_intent": conversation_intent.value,
                "confidence": round(best_score, 3),
            },
        )

        return {
            "intent": conversation_intent,
            "semantic_intent": best_intent,
            "confidence": best_score,
            "method": "semantic_router",
        }

    def is_non_empathy_intent(self, semantic_intent: str) -> bool:
        """
        感情系以外のIntentかどうかを判定する。
        これに該当する場合、emotion_scoresをリセットして
        StructuralAnalyzerのEmpathyモード誤爆を防ぐ。
        """
        return semantic_intent in ("summarize", "deep_dive", "knowledge", "chat")


# SemanticRouter シングルトン
semantic_router = SemanticRouter()


class IntentRouter:
    """
    Intent Router (仮説駆動型意図分類器)

    ユーザー入力を文脈と前回のインタラクション結果を踏まえて分類する。
    単一カテゴリの決め打ちではなく、「仮説リスト」と「確信度」を返し、
    確信度が低い場合はPROBE（探り）を推奨する。

    FASTモデルを使用して低レイテンシで処理。
    LLMが利用できない場合はキーワードベースのフォールバックを使用。
    """

    def __init__(self):
        self._provider: Optional[LLMProvider] = None

    def _get_provider(self) -> Optional[LLMProvider]:
        """LLMプロバイダーを取得（遅延初期化）"""
        if self._provider is None:
            try:
                self._provider = llm_manager.get_client(LLMUsageRole.FAST)
            except Exception:
                pass
        return self._provider

    async def classify(
        self,
        input_text: str,
        prev_context: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        文脈を考慮した仮説駆動型の意図分類

        Args:
            input_text: ユーザー入力
            prev_context: 前回のコンテキスト {
                "previous_intent": str,
                "previous_response": str,
            }

        Returns:
            {
                "intent": ConversationIntent,       # 最終的な意図（probeの場合あり）
                "confidence": float,                 # 主仮説の確信度
                "primary_intent": ConversationIntent,
                "secondary_intent": ConversationIntent,
                "primary_confidence": float,
                "secondary_confidence": float,
                "previous_evaluation": PreviousEvaluation,
                "needs_probing": bool,
                "reasoning": str,
            }
        """
        logger.info(
            "classify started",
            metadata={
                "input_preview": input_text[:80],
                "has_prev_context": prev_context is not None,
            },
        )

        # ── Semantic Router: 短い入力の先行判定 ──
        # 50文字以下の入力はLLMに渡す前にEmbeddingベースで分類する。
        # 「要約して」「教えて」などの明確な指示がEmpathyに誤爆するのを防ぐ。
        if len(input_text.strip()) <= semantic_router.SHORT_INPUT_MAX_LEN:
            try:
                sr_result = await semantic_router.route(input_text)
                if sr_result:
                    intent = sr_result["intent"]
                    confidence = float(sr_result["confidence"])
                    logger.info(
                        "classify completed (semantic_router)",
                        metadata={
                            "intent": intent.value,
                            "semantic_intent": sr_result["semantic_intent"],
                            "confidence": confidence,
                            "method": "semantic_router",
                        },
                    )
                    return {
                        "intent": intent,
                        "confidence": confidence,
                        "primary_intent": intent,
                        "secondary_intent": ConversationIntent.CHAT,
                        "primary_confidence": confidence,
                        "secondary_confidence": 0.0,
                        "previous_evaluation": PreviousEvaluation.NONE,
                        "needs_probing": False,
                        "reasoning": f"SemanticRouter: {sr_result['semantic_intent']} (cos={confidence:.3f})",
                    }
            except Exception as sr_err:
                logger.debug(
                    "SemanticRouter pre-classification failed (non-critical)",
                    metadata={"error": str(sr_err)},
                )

        provider = self._get_provider()
        if not provider:
            result = self._fallback_classify(input_text)
            logger.info(
                "classify completed (fallback)",
                metadata={
                    "intent": result["intent"].value,
                    "confidence": result["confidence"],
                    "method": "keyword_fallback",
                },
            )
            return result

        # 文脈情報の構築
        context_str = ""
        if prev_context:
            prev_intent = prev_context.get("previous_intent", "none")
            prev_response = prev_context.get("previous_response", "none")
            # レスポンスは先頭200文字に切り詰めてトークン節約
            context_str = (
                f"Previous Intent: {prev_intent}\n"
                f"Previous Response: {prev_response[:200]}..."
            )

        full_input = f"{context_str}\nCurrent Input: {input_text}" if context_str else input_text

        try:
            await provider.initialize()
            result = await provider.generate_json(
                messages=[
                    {"role": "system", "content": self._get_system_prompt()},
                    {"role": "user", "content": full_input},
                ],
                temperature=0.2,
            )
            parsed = self._parse_hypothesis_result(result)
            logger.info(
                "classify completed",
                metadata={
                    "intent": parsed["intent"].value,
                    "primary_intent": parsed["primary_intent"].value,
                    "primary_confidence": parsed["primary_confidence"],
                    "secondary_intent": parsed["secondary_intent"].value,
                    "secondary_confidence": parsed["secondary_confidence"],
                    "needs_probing": parsed["needs_probing"],
                    "method": "llm",
                },
            )
            return parsed
        except Exception as e:
            logger.warning(
                "classify failed, using fallback",
                metadata={"error": str(e)},
            )
            return self._fallback_classify(input_text)

    def _get_system_prompt(self) -> str:
        return ROUTER_PROMPT

    def _parse_hypothesis_result(self, result: dict) -> Dict[str, Any]:
        """LLMの仮説出力をパース"""
        intent_map = {
            "chat": ConversationIntent.CHAT,
            "state_share": ConversationIntent.STATE_SHARE,
            "empathy": ConversationIntent.EMPATHY,
            "knowledge": ConversationIntent.KNOWLEDGE,
            "deep_dive": ConversationIntent.DEEP_DIVE,
            "brainstorm": ConversationIntent.BRAINSTORM,
            "summarize": ConversationIntent.SUMMARIZE,
        }

        eval_map = {
            "positive": PreviousEvaluation.POSITIVE,
            "negative": PreviousEvaluation.NEGATIVE,
            "pivot": PreviousEvaluation.PIVOT,
            "none": PreviousEvaluation.NONE,
        }

        primary_str = result.get("primary_intent", "chat").lower()
        secondary_str = result.get("secondary_intent", "chat").lower()
        primary_intent = intent_map.get(primary_str, ConversationIntent.CHAT)
        secondary_intent = intent_map.get(secondary_str, ConversationIntent.CHAT)

        primary_confidence = self._clamp_confidence(result.get("primary_confidence", 0.5))
        secondary_confidence = self._clamp_confidence(result.get("secondary_confidence", 0.3))

        needs_probing = bool(result.get("needs_probing", False))
        previous_evaluation = eval_map.get(
            result.get("previous_evaluation", "none"),
            PreviousEvaluation.NONE,
        )
        reasoning = result.get("reasoning", "")

        # 最終的な意図を決定: needs_probingがtrueなら"probe"を採用
        if needs_probing:
            final_intent = ConversationIntent.PROBE
        else:
            final_intent = primary_intent

        return {
            "intent": final_intent,
            "confidence": primary_confidence,
            "primary_intent": primary_intent,
            "secondary_intent": secondary_intent,
            "primary_confidence": primary_confidence,
            "secondary_confidence": secondary_confidence,
            "previous_evaluation": previous_evaluation,
            "needs_probing": needs_probing,
            "reasoning": reasoning,
        }

    @staticmethod
    def _clamp_confidence(value: Any) -> float:
        """確信度を0.0〜1.0にクランプ"""
        if not isinstance(value, (int, float)):
            return 0.5
        return max(0.0, min(1.0, float(value)))

    def _fallback_classify(self, input_text: str) -> Dict[str, Any]:
        """キーワードベースのフォールバック分類（仮説形式で返す）"""
        # PROBEはキーワードマッチの対象外なので、基本6カテゴリのみスコアリング
        base_intents = [
            ConversationIntent.CHAT,
            ConversationIntent.STATE_SHARE,
            ConversationIntent.EMPATHY,
            ConversationIntent.KNOWLEDGE,
            ConversationIntent.DEEP_DIVE,
            ConversationIntent.BRAINSTORM,
        ]
        scores = {intent: 0.0 for intent in base_intents}

        for intent, keywords in _KEYWORD_MAP.items():
            if intent in scores:
                for kw in keywords:
                    if kw in input_text:
                        scores[intent] += 1.0

        # スコア順にソート
        sorted_intents = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        primary_intent, primary_score = sorted_intents[0]
        secondary_intent, secondary_score = sorted_intents[1]

        if primary_score == 0:
            # どのキーワードにもマッチしない場合はchat
            return {
                "intent": ConversationIntent.CHAT,
                "confidence": 0.3,
                "primary_intent": ConversationIntent.CHAT,
                "secondary_intent": ConversationIntent.CHAT,
                "primary_confidence": 0.3,
                "secondary_confidence": 0.0,
                "previous_evaluation": PreviousEvaluation.NONE,
                "needs_probing": False,
                "reasoning": "No keywords matched, defaulting to chat.",
            }

        # スコアを正規化して信頼度とする
        total = sum(scores.values())
        primary_confidence = min(primary_score / total, 0.7) if total > 0 else 0.3
        secondary_confidence = min(secondary_score / total, 0.5) if total > 0 else 0.0

        # 上位2つの確信度が近い場合はprobingを推奨
        needs_probing = (
            primary_confidence - secondary_confidence < 0.15
            and secondary_confidence > 0.1
        )

        if needs_probing:
            final_intent = ConversationIntent.PROBE
        else:
            final_intent = primary_intent

        return {
            "intent": final_intent,
            "confidence": primary_confidence,
            "primary_intent": primary_intent,
            "secondary_intent": secondary_intent,
            "primary_confidence": primary_confidence,
            "secondary_confidence": secondary_confidence,
            "previous_evaluation": PreviousEvaluation.NONE,
            "needs_probing": needs_probing,
            "reasoning": f"Keyword fallback: {primary_intent.value}={primary_score}, {secondary_intent.value}={secondary_score}",
        }


# シングルトンインスタンス
intent_router = IntentRouter()
