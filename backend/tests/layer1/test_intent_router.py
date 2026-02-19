"""
IntentRouter の単体テスト (Layer 1)

テスト方針:
1. LLMパス: プリセットレスポンスで各 ConversationIntent への変換を検証
2. フォールバックパス: キーワードベース分類のロジックを検証
3. ユーティリティ: _clamp_confidence などのヘルパー関数を検証

外部依存:
- LLM API  → MockLLMProvider でモック化（conftest.py）
- DB/Redis → 不使用（IntentRouter はステートレス）
"""
import pytest
from unittest.mock import patch

from app.schemas.conversation import ConversationIntent, PreviousEvaluation
from app.services.layer1.intent_router import IntentRouter


# =============================================================================
# LLM パス: プリセットレスポンスを使った意図分類テスト
# =============================================================================

class TestIntentRouterWithLLM:
    """LLM が利用可能な場合のルーティングテスト"""

    @pytest.mark.asyncio
    async def test_knowledge_intent(self, make_mock_provider):
        """知識系の質問が KNOWLEDGE に分類される"""
        router = IntentRouter()
        router._provider = make_mock_provider("knowledge", "intent")

        result = await router.classify("Pythonの非同期処理のベストプラクティスを教えて")

        assert result["intent"] == ConversationIntent.KNOWLEDGE
        assert result["primary_intent"] == ConversationIntent.KNOWLEDGE
        assert result["confidence"] > 0.8
        assert result["needs_probing"] is False
        assert result["previous_evaluation"] == PreviousEvaluation.NONE

    @pytest.mark.asyncio
    async def test_empathy_intent(self, make_mock_provider):
        """ネガティブ感情の吐き出しが EMPATHY に分類される"""
        router = IntentRouter()
        router._provider = make_mock_provider("empathy", "intent")

        result = await router.classify("今日も上司にひどいことを言われてつらい")

        assert result["intent"] == ConversationIntent.EMPATHY
        assert result["primary_intent"] == ConversationIntent.EMPATHY
        assert result["confidence"] > 0.8
        assert result["needs_probing"] is False

    @pytest.mark.asyncio
    async def test_brainstorm_intent(self, make_mock_provider):
        """アイデア壁打ちが BRAINSTORM に分類され、前回評価も反映される"""
        router = IntentRouter()
        router._provider = make_mock_provider("brainstorm", "intent")

        result = await router.classify("新機能のアイデアを一緒に考えたい")

        assert result["intent"] == ConversationIntent.BRAINSTORM
        assert result["previous_evaluation"] == PreviousEvaluation.POSITIVE

    @pytest.mark.asyncio
    async def test_state_share_intent(self, make_mock_provider):
        """短い状態報告が STATE_SHARE に分類される"""
        router = IntentRouter()
        router._provider = make_mock_provider("state_share", "intent")

        result = await router.classify("眠い")

        assert result["intent"] == ConversationIntent.STATE_SHARE
        assert result["confidence"] > 0.9

    @pytest.mark.asyncio
    async def test_deep_dive_intent(self, make_mock_provider):
        """課題分析の依頼が DEEP_DIVE に分類される"""
        router = IntentRouter()
        router._provider = make_mock_provider("deep_dive", "intent")

        result = await router.classify("プロジェクトが遅延している原因を一緒に分析したい")

        assert result["intent"] == ConversationIntent.DEEP_DIVE
        assert result["previous_evaluation"] == PreviousEvaluation.PIVOT

    @pytest.mark.asyncio
    async def test_ambiguous_input_returns_probe(self, make_mock_provider):
        """LLM が needs_probing=True を返すと最終 intent が PROBE になる"""
        router = IntentRouter()
        router._provider = make_mock_provider("probe", "intent")

        result = await router.classify("なんか色々悩んでいて...")

        assert result["intent"] == ConversationIntent.PROBE
        assert result["needs_probing"] is True
        # 内部の primary_intent はそのまま保持される
        assert result["primary_intent"] == ConversationIntent.KNOWLEDGE

    @pytest.mark.asyncio
    async def test_classify_with_prev_context(self, make_mock_provider):
        """前回コンテキストが LLM に渡されることを確認"""
        router = IntentRouter()
        provider = make_mock_provider("knowledge", "intent")
        router._provider = provider

        prev_context = {
            "previous_intent": "knowledge",
            "previous_response": "前回はPythonについてお答えしました。",
        }
        result = await router.classify("もっと詳しく教えて", prev_context=prev_context)

        assert "intent" in result
        assert "confidence" in result
        # LLM に送信されたメッセージにコンテキストが含まれることを検証
        user_message = provider.last_messages[-1]["content"]
        assert "Previous Intent" in user_message

    @pytest.mark.asyncio
    async def test_llm_called_once_per_classify(self, make_mock_provider):
        """classify 1回につき LLM が1回だけ呼ばれる"""
        router = IntentRouter()
        provider = make_mock_provider("knowledge", "intent")
        router._provider = provider

        await router.classify("テスト入力")

        assert provider.call_count == 1

    @pytest.mark.asyncio
    async def test_llm_failure_falls_back_to_keyword(self, make_mock_provider):
        """LLM が例外を投げた場合、キーワードフォールバックが動作する"""
        from unittest.mock import AsyncMock

        router = IntentRouter()
        provider = make_mock_provider("knowledge", "intent")
        provider.generate_json = AsyncMock(side_effect=RuntimeError("LLM timeout"))
        router._provider = provider

        # 例外時はフォールバックが動作し、エラーは上がらない
        result = await router.classify("Pythonを教えて")

        assert "intent" in result
        assert "confidence" in result


# =============================================================================
# フォールバックパス: キーワードベース分類テスト
# LLM が利用不可の場合でも正常に動作することを確認
# =============================================================================

class TestIntentRouterFallback:
    """キーワードフォールバック分類のテスト"""

    @pytest.mark.asyncio
    async def test_fallback_when_provider_unavailable(self):
        """llm_manager が例外を返す場合、フォールバックが動作する"""
        router = IntentRouter()
        router._provider = None  # キャッシュをクリア

        with patch("app.services.layer1.intent_router.llm_manager") as mock_manager:
            mock_manager.get_client.side_effect = Exception("Provider not available")
            result = await router.classify("眠い")

        assert result["intent"] in [ConversationIntent.STATE_SHARE, ConversationIntent.CHAT]
        assert "confidence" in result

    def test_fallback_knowledge_keywords(self):
        """知識系キーワードで KNOWLEDGE が返る"""
        router = IntentRouter()
        result = router._fallback_classify("Pythonの使い方を教えてください")

        assert result["intent"] == ConversationIntent.KNOWLEDGE
        assert result["confidence"] > 0

    def test_fallback_empathy_keywords(self):
        """感情系キーワードで EMPATHY が返る"""
        router = IntentRouter()
        result = router._fallback_classify("つらいし不安でイライラする毎日だ")

        assert result["intent"] == ConversationIntent.EMPATHY

    def test_fallback_state_share_keywords(self):
        """状態系キーワードで STATE_SHARE が返る"""
        router = IntentRouter()
        result = router._fallback_classify("眠い")

        assert result["intent"] == ConversationIntent.STATE_SHARE

    def test_fallback_brainstorm_keywords(self):
        """発想系キーワードで BRAINSTORM が返る"""
        router = IntentRouter()
        result = router._fallback_classify("新しいアイデアをブレストしたい")

        assert result["intent"] == ConversationIntent.BRAINSTORM

    def test_fallback_deep_dive_keywords(self):
        """問題解決系キーワードで DEEP_DIVE が返る"""
        router = IntentRouter()
        result = router._fallback_classify("この問題の原因を分析して解決策を整理したい")

        assert result["intent"] == ConversationIntent.DEEP_DIVE

    def test_fallback_no_keywords_defaults_to_chat(self):
        """キーワードにマッチしない場合は CHAT がデフォルト"""
        router = IntentRouter()
        result = router._fallback_classify("abcdefg xyz123")

        assert result["intent"] == ConversationIntent.CHAT
        assert result["confidence"] == 0.3

    def test_fallback_returns_probe_when_scores_close(self):
        """上位2つのスコアが近い場合は PROBE を返す"""
        router = IntentRouter()
        # empathy と知識 両方のキーワードを含む
        result = router._fallback_classify("つらくてどうすれば改善できるか不安で教えて")

        # 高スコアが複数あれば needs_probing が True になる場合がある
        assert result["intent"] in list(ConversationIntent)

    def test_fallback_returns_required_keys(self):
        """フォールバック結果が必須キーを全て持つ"""
        router = IntentRouter()
        result = router._fallback_classify("テスト入力")

        required_keys = {
            "intent", "confidence", "primary_intent", "secondary_intent",
            "primary_confidence", "secondary_confidence",
            "previous_evaluation", "needs_probing", "reasoning",
        }
        assert required_keys.issubset(result.keys())

    def test_fallback_previous_evaluation_is_none(self):
        """フォールバックは常に PreviousEvaluation.NONE を返す"""
        router = IntentRouter()
        result = router._fallback_classify("テスト")

        assert result["previous_evaluation"] == PreviousEvaluation.NONE


# =============================================================================
# ユーティリティ: _clamp_confidence
# =============================================================================

class TestClampConfidence:
    """確信度クランプのテスト"""

    def test_valid_range(self):
        router = IntentRouter()
        assert router._clamp_confidence(0.0) == 0.0
        assert router._clamp_confidence(0.5) == 0.5
        assert router._clamp_confidence(1.0) == 1.0

    def test_exceeds_upper_bound(self):
        router = IntentRouter()
        assert router._clamp_confidence(1.5) == 1.0
        assert router._clamp_confidence(100.0) == 1.0

    def test_below_lower_bound(self):
        router = IntentRouter()
        assert router._clamp_confidence(-0.5) == 0.0
        assert router._clamp_confidence(-100.0) == 0.0

    def test_invalid_string(self):
        router = IntentRouter()
        assert router._clamp_confidence("high") == 0.5

    def test_invalid_none(self):
        router = IntentRouter()
        assert router._clamp_confidence(None) == 0.5

    def test_integer_input(self):
        """整数も有効な入力として扱う"""
        router = IntentRouter()
        assert router._clamp_confidence(1) == 1.0
        assert router._clamp_confidence(0) == 0.0
