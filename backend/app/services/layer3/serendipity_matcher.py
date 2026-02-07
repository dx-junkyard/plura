"""
MINDYARD - Serendipity Matcher
Layer 3: ユーザーが「検索」する前に、関連情報を提示するプッシュ型レコメンデーション
"""
from typing import Dict, List, Optional
import uuid

from app.services.layer1.context_analyzer import context_analyzer
from app.services.layer3.knowledge_store import knowledge_store


class SerendipityMatcher:
    """
    Serendipity Matcher (セレンディピティ・エンジン)

    機能:
    - 入力中のテキストからリアルタイムで関連インサイトを検索
    - 控えめな「副作用的」レコメンデーション
    - ユーザーの文脈に基づいたパーソナライズ
    """

    def __init__(self):
        self.min_content_length = 20  # 最低限必要な文字数
        self.recommendation_limit = 3  # 推奨表示数
        self.score_threshold = 0.65  # 類似度閾値（やや緩め）

    async def find_related_insights(
        self,
        current_input: str,
        user_id: Optional[uuid.UUID] = None,
        exclude_ids: Optional[List[str]] = None,
    ) -> Dict:
        """
        現在の入力に関連するインサイトを検索

        Args:
            current_input: ユーザーが入力中のテキスト
            user_id: ユーザーID（パーソナライズ用、将来実装）
            exclude_ids: 除外するインサイトID

        Returns:
            {
                "has_recommendations": bool,
                "recommendations": List[Dict],
                "trigger_reason": str,
            }
        """
        # 最低文字数チェック
        if len(current_input.strip()) < self.min_content_length:
            return {
                "has_recommendations": False,
                "recommendations": [],
                "trigger_reason": "insufficient_content",
            }

        # 類似インサイトを検索
        current_context = await context_analyzer.analyze(current_input)
        filter_tags = self._build_filter_tags(current_context)

        similar_insights = await knowledge_store.search_similar(
            query=current_input,
            limit=self.recommendation_limit + len(exclude_ids or []),
            score_threshold=self.score_threshold,
            filter_tags=filter_tags,
        )

        # 除外IDをフィルタリング
        if exclude_ids:
            similar_insights = [
                insight for insight in similar_insights
                if insight.get("insight_id") not in exclude_ids
            ]

        # 推奨数に制限
        recommendations = similar_insights[: self.recommendation_limit]

        if not recommendations:
            return {
                "has_recommendations": False,
                "recommendations": [],
                "trigger_reason": "no_matches",
            }

        # 推奨メッセージの生成
        formatted_recommendations = [
            self._format_recommendation(rec) for rec in recommendations
        ]

        return {
            "has_recommendations": True,
            "recommendations": formatted_recommendations,
            "trigger_reason": "similar_experiences_found",
            "display_message": self._generate_display_message(len(recommendations)),
        }

    def _format_recommendation(self, insight: Dict) -> Dict:
        """推奨インサイトをUI表示用にフォーマット"""
        return {
            "id": insight.get("insight_id"),
            "title": insight.get("title"),
            "summary": insight.get("summary"),
            "topics": insight.get("topics", []),
            "relevance_score": round(insight.get("score", 0) * 100),
            "preview": self._generate_preview(insight),
        }

    def _generate_preview(self, insight: Dict) -> str:
        """インサイトのプレビューテキストを生成"""
        summary = insight.get("summary", "")
        if len(summary) > 100:
            return summary[:100] + "..."
        return summary

    def _generate_display_message(self, count: int) -> str:
        """表示メッセージを生成"""
        if count == 1:
            return "似た経験を持つ人がいます"
        return f"{count}件の関連する知見が見つかりました"

    def _build_filter_tags(self, current_context: Dict) -> List[str]:
        """現在入力の解析結果から検索タグを構築"""
        tags = current_context.get("tags", [])
        topics = current_context.get("topics", [])

        merged = []
        for item in tags + topics:
            if isinstance(item, str):
                value = item.strip()
                if value and value not in merged:
                    merged.append(value)
        return merged[:8]


# シングルトンインスタンス
serendipity_matcher = SerendipityMatcher()
