"""
MINDYARD - Serendipity Matcher
Layer 3: ユーザーが「検索」する前に、関連情報を提示するプッシュ型レコメンデーション
"""
from typing import Dict, List, Optional
import uuid

from sqlalchemy import select

from app.services.layer1.context_analyzer import context_analyzer
from app.services.layer3.knowledge_store import knowledge_store

# デモ用定数
DEMO_TAG = "demo_flash_team"
DEMO_TEAM_MIN_MEMBERS = 3


class SerendipityMatcher:
    """
    Serendipity Matcher (セレンディピティ・エンジン)

    機能:
    - 入力中のテキストからリアルタイムで関連インサイトを検索
    - 控えめな「副作用的」レコメンデーション
    - ユーザーの文脈に基づいたパーソナライズ
    - デモ用Flash Team Formation バイパス
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
        # --- Demo bypass: Flash Team Formation ---
        team_proposal = await self._check_flash_team(user_id)
        if team_proposal:
            return team_proposal

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

    async def _check_flash_team(
        self, current_user_id: Optional[uuid.UUID] = None
    ) -> Optional[Dict]:
        """
        デモ用Flash Team Formationバイパス

        InsightCard の keywords (tags) に DEMO_TAG が含まれるレコードを検索し、
        異なるユーザーが3名以上存在する場合に TEAM_PROPOSAL を生成する。

        通常のマッチングロジックには影響しない。
        """
        from app.db.base import async_session_maker
        from app.models.insight import InsightCard, InsightStatus

        try:
            async with async_session_maker() as session:
                # demo_flash_team タグを持つ公開済みインサイトを検索
                stmt = (
                    select(InsightCard)
                    .where(
                        InsightCard.status == InsightStatus.APPROVED,
                        InsightCard.tags.any(DEMO_TAG),
                    )
                )
                result = await session.execute(stmt)
                demo_insights = result.scalars().all()

                if not demo_insights:
                    return None

                # 異なるユーザーでグルーピング
                user_insights: Dict[str, List] = {}
                for insight in demo_insights:
                    uid = str(insight.author_id)
                    if uid not in user_insights:
                        user_insights[uid] = []
                    user_insights[uid].append(insight)

                # 現在のユーザーを除外してカウント
                other_user_ids = [
                    uid for uid in user_insights
                    if current_user_id is None or uid != str(current_user_id)
                ]

                if len(other_user_ids) < DEMO_TEAM_MIN_MEMBERS:
                    return None

                # 3名を選出（先頭3名）
                selected_user_ids = other_user_ids[:DEMO_TEAM_MIN_MEMBERS]

                # 各メンバーの代表インサイトからプロフィールを構築
                team_members = []
                all_topics: List[str] = []
                roles = ["エンジニア", "デザイナー", "ドメインエキスパート"]

                for i, uid in enumerate(selected_user_ids):
                    representative = user_insights[uid][0]
                    member_topics = representative.topics or []
                    all_topics.extend(member_topics)

                    # ユーザー情報を取得
                    from app.models.user import User
                    user_stmt = select(User).where(User.id == uuid.UUID(uid))
                    user_result = await session.execute(user_stmt)
                    user = user_result.scalar_one_or_none()

                    team_members.append({
                        "user_id": uid,
                        "display_name": (
                            user.display_name if user and user.display_name
                            else f"メンバー {i + 1}"
                        ),
                        "role": roles[i] if i < len(roles) else "メンバー",
                        "avatar_url": user.avatar_url if user else None,
                    })

                # ユニークなトピックスを集約
                unique_topics = list(dict.fromkeys(all_topics))[:5]

                # プロジェクト名を生成
                project_name = self._generate_project_name(unique_topics)

                # TEAM_PROPOSAL Recommendation を構築
                proposal_id = str(uuid.uuid4())
                recommendation = {
                    "id": proposal_id,
                    "title": "Flash Team が結成可能です",
                    "summary": (
                        f"{len(team_members)}名の専門家が見つかりました。"
                        "異なる視点を持つメンバーによる最適なチームを提案します。"
                    ),
                    "topics": unique_topics,
                    "relevance_score": 95,
                    "preview": (
                        "技術 × デザイン × 課題 の最適な組み合わせが見つかりました。"
                        "AIが分析した結果、このチームは高い相乗効果が期待できます。"
                    ),
                    "category": "TEAM_PROPOSAL",
                    "reason": (
                        "技術 × デザイン × 課題 の最適な組み合わせが見つかりました。"
                        "それぞれの専門領域が補完し合い、"
                        "プロジェクトの成功確率を最大化します。"
                    ),
                    "team_members": team_members,
                    "project_name": project_name,
                }

                return {
                    "has_recommendations": True,
                    "recommendations": [recommendation],
                    "trigger_reason": "flash_team_formed",
                    "display_message": "あなたに最適なチームが見つかりました",
                }

        except Exception:
            # DB 接続エラー等はスキップして通常フローに戻す
            return None

    def _generate_project_name(self, topics: List[str]) -> str:
        """トピックスからプロジェクト名を生成"""
        if not topics:
            return "Flash Team Project"
        topic_str = " × ".join(topics[:3])
        return f"{topic_str} プロジェクト"

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
