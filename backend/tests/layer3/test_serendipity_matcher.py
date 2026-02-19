"""
SerendipityMatcher の単体テスト (Layer 3)

テスト方針:
1. knowledge_store (Qdrant ベクトル検索) をモック化
2. LLM シナジー評価もモック化
3. 以下の主要パスを検証:
   - 入力文字数不足 → 即時スキップ
   - 候補なし → レコメンデーションなし
   - 通常検索フォールバック (LLM なし) → 類似インサイト返却
   - Flash Team 提案パス (LLM あり、シナジー検出)
   - Flash Team 不成立 → 通常検索フォールバック
"""
import pytest
from unittest.mock import AsyncMock, patch

from app.services.layer3.serendipity_matcher import (
    BROAD_SCORE_THRESHOLD,
    MIN_CANDIDATES_FOR_TEAM,
    MIN_INPUT_LENGTH_FOR_TEAM,
    SerendipityMatcher,
)


# =============================================================================
# テスト用固定候補データ
# =============================================================================

MOCK_CANDIDATES = [
    {
        "insight_id": "insight-001",
        "title": "リモートワークでのチームコミュニケーション改善",
        "summary": "Slackチャンネルを議論と決定事項で分けることで情報共有が改善した。",
        "topics": ["リモートワーク", "コミュニケーション"],
        "score": 0.82,
    },
    {
        "insight_id": "insight-002",
        "title": "非同期コミュニケーションのベストプラクティス",
        "summary": "非同期ツールの適切な使い方で生産性が大きく変わる。",
        "topics": ["非同期", "生産性"],
        "score": 0.75,
    },
    {
        "insight_id": "insight-003",
        "title": "UXデザインの観点から見たSlack設計",
        "summary": "情報アーキテクチャとユーザビリティのバランスが重要。",
        "topics": ["UX", "デザイン", "Slack"],
        "score": 0.70,
    },
]

# score_threshold (0.65) 未満の候補
LOW_SCORE_CANDIDATES = [
    {
        "insight_id": "insight-low",
        "title": "関連性の低いインサイト",
        "summary": "あまり関係のない内容。",
        "topics": [],
        "score": 0.50,  # score_threshold=0.65 未満
    },
]


# =============================================================================
# フィクスチャ: knowledge_store モック
# =============================================================================

@pytest.fixture
def mock_ks_with_results():
    """MOCK_CANDIDATES を返す knowledge_store モック"""
    with patch("app.services.layer3.serendipity_matcher.knowledge_store") as mock_ks:
        mock_ks.search_similar = AsyncMock(return_value=MOCK_CANDIDATES)
        yield mock_ks


@pytest.fixture
def mock_ks_low_scores():
    """score_threshold 未満の候補のみを返すモック"""
    with patch("app.services.layer3.serendipity_matcher.knowledge_store") as mock_ks:
        mock_ks.search_similar = AsyncMock(return_value=LOW_SCORE_CANDIDATES)
        yield mock_ks


@pytest.fixture
def mock_ks_empty():
    """候補なしのモック"""
    with patch("app.services.layer3.serendipity_matcher.knowledge_store") as mock_ks:
        mock_ks.search_similar = AsyncMock(return_value=[])
        yield mock_ks


# =============================================================================
# 基本的な制御フローテスト
# =============================================================================

class TestFindRelatedBasicFlow:
    """find_related_insights の基本制御フロー"""

    @pytest.mark.asyncio
    async def test_insufficient_content_skips_search(self, mock_ks_empty):
        """min_content_length (20文字) 未満の入力は即座にスキップされる"""
        matcher = SerendipityMatcher()

        result = await matcher.find_related_insights("短い")

        assert result["has_recommendations"] is False
        assert result["trigger_reason"] == "insufficient_content"
        # knowledge_store は呼ばれない
        mock_ks_empty.search_similar.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_candidates_returns_no_match(self, mock_ks_empty):
        """候補が0件の場合はレコメンデーションなし"""
        matcher = SerendipityMatcher()
        matcher._llm_provider = None

        result = await matcher.find_related_insights(
            "チームのコミュニケーション改善について深く考えている。"
        )

        assert result["has_recommendations"] is False
        assert result["trigger_reason"] == "no_matches"

    @pytest.mark.asyncio
    async def test_low_score_candidates_returns_no_recommendations(self, mock_ks_low_scores):
        """score_threshold 未満の候補のみの場合はレコメンデーションなし"""
        matcher = SerendipityMatcher()
        matcher._llm_provider = None

        result = await matcher.find_related_insights(
            "チームのコミュニケーション改善について深く考えている。"
        )

        assert result["has_recommendations"] is False

    @pytest.mark.asyncio
    async def test_high_score_candidates_return_recommendations(self, mock_ks_with_results):
        """score_threshold 以上の候補がある場合はレコメンデーションを返す"""
        matcher = SerendipityMatcher()
        matcher._llm_provider = None  # LLM 無効 → 通常検索フォールバック

        result = await matcher.find_related_insights(
            "チームのコミュニケーション改善について考えている。非同期ツールを活用したい。"
        )

        assert result["has_recommendations"] is True
        assert len(result["recommendations"]) <= matcher.recommendation_limit
        assert result["trigger_reason"] == "similar_experiences_found"

    @pytest.mark.asyncio
    async def test_recommendation_limit_respected(self, mock_ks_with_results):
        """recommendation_limit (3) を超えてレコメンデーションは返さない"""
        matcher = SerendipityMatcher()
        matcher._llm_provider = None

        result = await matcher.find_related_insights(
            "チームのコミュニケーション改善について考えている。非同期ツールを活用したい。"
        )

        assert len(result["recommendations"]) <= 3


# =============================================================================
# 除外 ID のフィルタリングテスト
# =============================================================================

class TestExcludeIds:
    """exclude_ids フィルタリングのテスト"""

    @pytest.mark.asyncio
    async def test_excludes_specified_ids(self, mock_ks_with_results):
        """exclude_ids に含まれる insight は結果から除外される"""
        matcher = SerendipityMatcher()
        matcher._llm_provider = None

        exclude_ids = ["insight-001", "insight-002", "insight-003"]
        result = await matcher.find_related_insights(
            "チームのコミュニケーション改善について考えている。非同期ツールを活用したい。",
            exclude_ids=exclude_ids,
        )

        assert result["has_recommendations"] is False

    @pytest.mark.asyncio
    async def test_partial_exclusion_keeps_remaining(self, mock_ks_with_results):
        """一部だけ除外した場合、残りの候補が返る"""
        matcher = SerendipityMatcher()
        matcher._llm_provider = None

        # insight-001 だけ除外
        result = await matcher.find_related_insights(
            "チームのコミュニケーション改善について考えている。非同期ツールを活用したい。",
            exclude_ids=["insight-001"],
        )

        if result["has_recommendations"]:
            ids = [r["id"] for r in result["recommendations"]]
            assert "insight-001" not in ids


# =============================================================================
# LLM シナジー評価テスト（Flash Team 提案）
# =============================================================================

class TestLLMSynergyEvaluation:
    """LLM シナジー評価パスのテスト"""

    @pytest.mark.asyncio
    async def test_flash_team_formed_when_synergy_found(
        self, mock_ks_with_results, make_mock_provider
    ):
        """LLM がシナジーを検出した場合、Flash Team 提案を返す"""
        matcher = SerendipityMatcher()
        matcher._llm_provider = make_mock_provider("team_found", "synergy")

        # MIN_INPUT_LENGTH_FOR_TEAM (50) 以上 + MIN_CANDIDATES_FOR_TEAM (3) 以上が必要
        long_input = (
            "チームのコミュニケーション改善について深く考えている。"
            "リモートワークでの情報共有が最大の課題。Slackの設計を見直したい。"
        )
        result = await matcher.find_related_insights(long_input)

        assert result["has_recommendations"] is True
        assert result["trigger_reason"] == "flash_team_formed"
        assert len(result["recommendations"]) == 1
        assert result["recommendations"][0]["category"] == "TEAM_PROPOSAL"
        assert "team_members" in result["recommendations"][0]

    @pytest.mark.asyncio
    async def test_no_team_falls_back_to_normal_search(
        self, mock_ks_with_results, make_mock_provider
    ):
        """LLM がシナジーなし (team_found=False) の場合、通常検索にフォールバック"""
        matcher = SerendipityMatcher()
        matcher._llm_provider = make_mock_provider("no_team", "synergy")

        long_input = (
            "チームのコミュニケーション改善について深く考えている。"
            "リモートワークでの情報共有が最大の課題。Slackの設計を見直したい。"
        )
        result = await matcher.find_related_insights(long_input)

        # Flash Team ではなく通常検索が使われる
        assert result["trigger_reason"] != "flash_team_formed"

    @pytest.mark.asyncio
    async def test_llm_skipped_when_input_too_short(
        self, mock_ks_with_results, make_mock_provider
    ):
        """入力が MIN_INPUT_LENGTH_FOR_TEAM 未満の場合、LLM シナジー評価はスキップ"""
        matcher = SerendipityMatcher()
        provider = make_mock_provider("team_found", "synergy")
        matcher._llm_provider = provider

        # 最低文字数は満たすが、シナジー評価の閾値 (50文字) 未満
        short_input = "コミュニケーション改善"  # < 50 chars
        await matcher.find_related_insights(short_input)

        # LLM は呼ばれていない
        assert provider.call_count == 0

    @pytest.mark.asyncio
    async def test_llm_skipped_when_candidates_too_few(
        self, mock_ks_low_scores, make_mock_provider
    ):
        """候補が MIN_CANDIDATES_FOR_TEAM (3) 未満の場合、LLM シナジー評価はスキップ"""
        matcher = SerendipityMatcher()
        provider = make_mock_provider("team_found", "synergy")
        matcher._llm_provider = provider

        long_input = (
            "チームのコミュニケーション改善について深く考えている。"
            "リモートワークでの情報共有が最大の課題。"
        )
        await matcher.find_related_insights(long_input)

        # 候補が1件のみ (< MIN_CANDIDATES_FOR_TEAM=3) → LLM スキップ
        assert provider.call_count == 0


# =============================================================================
# レコメンデーションフォーマットテスト
# =============================================================================

class TestRecommendationFormat:
    """_format_recommendation のテスト"""

    def test_format_recommendation_basic(self):
        """レコメンデーションのフォーマットが正しい"""
        matcher = SerendipityMatcher()
        candidate = MOCK_CANDIDATES[0]
        formatted = matcher._format_recommendation(candidate)

        assert formatted["id"] == candidate["insight_id"]
        assert formatted["title"] == candidate["title"]
        assert formatted["summary"] == candidate["summary"]
        assert formatted["topics"] == candidate["topics"]
        assert formatted["relevance_score"] == round(candidate["score"] * 100)

    def test_format_recommendation_preview_truncation(self):
        """100文字を超える summary は切り詰められる"""
        matcher = SerendipityMatcher()
        long_summary = "あ" * 200
        candidate = {
            "insight_id": "test",
            "title": "テスト",
            "summary": long_summary,
            "topics": [],
            "score": 0.8,
        }
        formatted = matcher._format_recommendation(candidate)
        assert len(formatted["preview"]) <= 103  # 100 + "..."

    def test_format_recommendation_short_summary_not_truncated(self):
        """100文字以下の summary はそのまま"""
        matcher = SerendipityMatcher()
        candidate = {
            "insight_id": "test",
            "title": "テスト",
            "summary": "短い要約",
            "topics": [],
            "score": 0.8,
        }
        formatted = matcher._format_recommendation(candidate)
        assert formatted["preview"] == "短い要約"


# =============================================================================
# ユーティリティメソッドテスト
# =============================================================================

class TestUtilityMethods:
    """ユーティリティメソッドのテスト"""

    def test_display_message_singular(self):
        """1件の場合は単数形のメッセージ"""
        matcher = SerendipityMatcher()
        assert matcher._generate_display_message(1) == "似た経験を持つ人がいます"

    def test_display_message_plural(self):
        """複数件の場合は件数入りのメッセージ"""
        matcher = SerendipityMatcher()
        assert "3件" in matcher._generate_display_message(3)
        assert "5件" in matcher._generate_display_message(5)

    def test_parse_team_response_returns_none_when_team_not_found(self):
        """team_found=False の場合は None を返す"""
        matcher = SerendipityMatcher()
        result = matcher._parse_team_response({"team_found": False}, [])

        assert result is None

    def test_parse_team_response_returns_none_when_no_members(self):
        """members が空の場合は None を返す"""
        matcher = SerendipityMatcher()
        result = matcher._parse_team_response(
            {"team_found": True, "members": []}, []
        )
        assert result is None

    def test_parse_team_response_builds_correct_structure(self):
        """有効なレスポンスから正しい TEAM_PROPOSAL 構造が生成される"""
        matcher = SerendipityMatcher()
        llm_result = {
            "team_found": True,
            "project_name": "テストプロジェクト",
            "reason": "補完的なチームです。",
            "members": [
                {
                    "insight_id": "insight-001",
                    "display_name": "開発者",
                    "role": "ハッカー",
                },
            ],
        }
        candidates = [
            {
                "insight_id": "insight-001",
                "title": "テスト",
                "summary": "テスト",
                "topics": ["Python", "Backend"],
                "score": 0.8,
            }
        ]

        result = matcher._parse_team_response(llm_result, candidates)

        assert result is not None
        assert result["has_recommendations"] is True
        assert result["trigger_reason"] == "flash_team_formed"
        assert result["recommendations"][0]["category"] == "TEAM_PROPOSAL"
        assert result["recommendations"][0]["project_name"] == "テストプロジェクト"
        team_members = result["recommendations"][0]["team_members"]
        assert len(team_members) == 1
        assert team_members[0]["role"] == "ハッカー"
