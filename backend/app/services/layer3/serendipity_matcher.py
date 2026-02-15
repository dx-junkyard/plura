"""
MINDYARD - Serendipity Matcher
Layer 3: ユーザーが「検索」する前に、関連情報を提示するプッシュ型レコメンデーション

Retrieve & Evaluate パターン:
1. Broad Retrieval: ベクトル検索で広く候補を集める
2. LLM Synergy Evaluation: LLMで補完関係（化学反応）を判定する
"""
import logging
import uuid
from typing import Any, Dict, List, Optional

from app.core.llm import extract_json_from_text, llm_manager
from app.core.llm_provider import LLMProvider, LLMUsageRole
from app.services.layer3.knowledge_store import knowledge_store

logger = logging.getLogger(__name__)

# LLM評価をスキップする閾値
MIN_INPUT_LENGTH_FOR_TEAM = 50  # チーム評価に必要な最低入力文字数
MIN_CANDIDATES_FOR_TEAM = 3    # チーム評価に必要な最低候補数

# Broad Retrieval パラメータ
BROAD_SEARCH_LIMIT = 10
BROAD_SCORE_THRESHOLD = 0.45

SYNERGY_SYSTEM_PROMPT = """\
あなたは「イノベーション・コーディネーター」です。
複数の人物のスキルや関心を分析し、異能のFlash Teamを結成する専門家です。

## あなたの使命
与えられた候補者リストの中から、現在のユーザーの課題を解決できる
「補完的なチーム」を発見してください。

## 評価基準（重要度順）
1. **役割の分散**: 「似た者同士」は低評価。以下の3つの役割が揃うほど高評価:
   - ハッカー（Tech）: 技術的な実装力を持つ人
   - ヒップスター（Design）: デザイン思考・UX・ユーザー視点を持つ人
   - ハスラー（Biz）: ビジネス・ドメイン知識・課題定義力を持つ人
2. **課題解決の具体性**: チームを組むことで、現在のユーザーの課題に対して
   具体的な解決アプローチが見えること。
3. **シナジーの存在**: 単に足し合わせるだけでなく、掛け合わせることで
   新しい価値が生まれる組み合わせであること。

## 出力ルール
- チーム結成が**可能**な場合のみ、以下のJSON形式で出力してください。
- チーム結成が**不可能**（候補者が似すぎている、課題が不明瞭など）な場合は、
  `{"team_found": false}` のみを出力してください。

## JSON出力フォーマット（チーム結成可能な場合）
```json
{
  "team_found": true,
  "project_name": "プロジェクト名（課題を端的に表す名前）",
  "reason": "このチームが有効な理由（補完関係の説明、2〜3文）",
  "members": [
    {
      "insight_id": "候補者のinsight_id",
      "display_name": "トピックスから推測される専門分野（例: フロントエンド開発者）",
      "role": "ハッカー/ヒップスター/ハスラー のいずれか"
    }
  ]
}
```

必ずJSONのみを出力してください。説明文や前置きは不要です。\
"""


class SerendipityMatcher:
    """
    Serendipity Matcher (セレンディピティ・エンジン)

    機能:
    - 入力中のテキストからリアルタイムで関連インサイトを検索
    - 控えめな「副作用的」レコメンデーション
    - LLMによるチームシナジー評価（Retrieve & Evaluate パターン）
    """

    def __init__(self):
        self.min_content_length = 20  # 最低限必要な文字数
        self.recommendation_limit = 3  # 推奨表示数
        self.score_threshold = 0.65  # 通常検索の類似度閾値
        self._llm_provider: Optional[LLMProvider] = None

    def _get_llm_provider(self) -> Optional[LLMProvider]:
        """LLMプロバイダーを取得（遅延初期化）"""
        if self._llm_provider is None:
            try:
                self._llm_provider = llm_manager.get_client(LLMUsageRole.BALANCED)
            except Exception:
                logger.warning("LLM provider not available for synergy evaluation")
        return self._llm_provider

    async def find_related_insights(
        self,
        current_input: str,
        user_id: Optional[uuid.UUID] = None,
        exclude_ids: Optional[List[str]] = None,
    ) -> Dict:
        """
        現在の入力に関連するインサイトを検索
        """
        stripped_input = current_input.strip()
        input_len = len(stripped_input)

        # 最低文字数チェック
        if input_len < self.min_content_length:
            return {
                "has_recommendations": False,
                "recommendations": [],
                "trigger_reason": "insufficient_content",
            }

        # --- Step 1: Broad Retrieval (広域探索) ---
        broad_candidates = await knowledge_store.search_similar(
            query=current_input,
            limit=BROAD_SEARCH_LIMIT,
            score_threshold=BROAD_SCORE_THRESHOLD,
            filter_tags=None,
        )

        # 除外IDをフィルタリング
        if exclude_ids:
            broad_candidates = [
                c for c in broad_candidates
                if c.get("insight_id") not in exclude_ids
            ]

        candidate_count = len(broad_candidates)
        # 【追加】Step 1 の結果をログ出力
        logger.info(f"[Step 1: Broad Retrieval] Found {candidate_count} candidates. (Threshold: {BROAD_SCORE_THRESHOLD})")

        # --- Step 2: LLM Synergy Evaluation (シナジー判定) ---
        # ガード節の判定状況をログ出力
        if input_len < MIN_INPUT_LENGTH_FOR_TEAM or candidate_count < MIN_CANDIDATES_FOR_TEAM:
            logger.info(
                f"[Step 2: LLM Skip] Criteria not met: Input length {input_len}/{MIN_INPUT_LENGTH_FOR_TEAM}, "
                f"Candidates {candidate_count}/{MIN_CANDIDATES_FOR_TEAM}"
            )
        else:
            # 【追加】LLM評価開始のログ
            logger.info(f"[Step 2: LLM Evaluation] Starting synergy analysis with {candidate_count} candidates...")
            
            team_proposal = await self._evaluate_team_synergy(
                current_input=stripped_input,
                candidates=broad_candidates,
            )
            
            if team_proposal:
                matched_members = len(team_proposal["recommendations"][0].get("team_members", []))
                # 【追加】マッチング成功時のログ
                logger.info(f"[Step 2: Success] Flash Team formed with {matched_members} members.")
                return team_proposal
            else:
                logger.info("[Step 2: LLM Finished] No synergy found between candidates.")

        # --- Fallback: 通常の類似検索結果を返す ---

        # --- Fallback: 通常の類似検索結果を返す ---
        # 通常閾値でフィルタリング
        recommendations = [
            c for c in broad_candidates
            if c.get("score", 0) >= self.score_threshold
        ][:self.recommendation_limit]

        if not recommendations:
            return {
                "has_recommendations": False,
                "recommendations": [],
                "trigger_reason": "no_matches",
            }

        formatted_recommendations = [
            self._format_recommendation(rec) for rec in recommendations
        ]

        return {
            "has_recommendations": True,
            "recommendations": formatted_recommendations,
            "trigger_reason": "similar_experiences_found",
            "display_message": self._generate_display_message(len(recommendations)),
        }

    async def _evaluate_team_synergy(
        self,
        current_input: str,
        candidates: List[Dict],
    ) -> Optional[Dict]:
        """
        LLMを用いてチームシナジーを評価する

        Args:
            current_input: ユーザーの入力テキスト
            candidates: Broad Retrieval で取得した候補リスト

        Returns:
            TEAM_PROPOSAL レコメンデーション辞書、またはチーム不成立時は None
        """
        provider = self._get_llm_provider()
        if not provider:
            return None

        # 候補情報をプロンプト用にフォーマット
        candidates_text = self._format_candidates_for_prompt(candidates)

        user_prompt = f"""\
## 現在のユーザーの入力（課題・関心）
{current_input}

## 候補者リスト（ベクトル検索で発見された関連インサイト）
{candidates_text}

上記の候補者から、現在のユーザーの課題を解決できる補完的なチームを
結成できるか判定してください。"""

        try:
            await provider.initialize()
            result = await provider.generate_json(
                messages=[
                    {"role": "system", "content": SYNERGY_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.4,
            )

            return self._parse_team_response(result, candidates)

        except Exception:
            # JSON パース失敗時は extract_json_from_text でリトライ
            try:
                response = await provider.generate_text(
                    messages=[
                        {"role": "system", "content": SYNERGY_SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.4,
                )
                parsed = extract_json_from_text(response.content)
                if parsed:
                    return self._parse_team_response(parsed, candidates)
            except Exception:
                logger.warning("LLM synergy evaluation failed", exc_info=True)

            return None

    def _format_candidates_for_prompt(self, candidates: List[Dict]) -> str:
        """候補リストをLLMプロンプト用テキストに変換"""
        lines = []
        for i, c in enumerate(candidates, 1):
            topics = ", ".join(c.get("topics", [])) or "なし"
            lines.append(
                f"{i}. [ID: {c.get('insight_id', 'unknown')}]\n"
                f"   タイトル: {c.get('title', '不明')}\n"
                f"   要約: {c.get('summary', '情報なし')}\n"
                f"   トピックス: {topics}\n"
                f"   類似度スコア: {c.get('score', 0):.2f}"
            )
        return "\n".join(lines)

    def _parse_team_response(
        self,
        llm_result: Dict[str, Any],
        candidates: List[Dict],
    ) -> Optional[Dict]:
        """
        LLMレスポンスを解析し、TEAM_PROPOSAL レコメンデーションを構築する

        Args:
            llm_result: LLMが返したJSONオブジェクト
            candidates: 元の候補リスト（追加情報の補完用）

        Returns:
            TEAM_PROPOSAL 形式のレコメンデーション辞書、またはチーム不成立時は None
        """
        if not llm_result.get("team_found"):
            return None

        members_raw = llm_result.get("members", [])
        if not members_raw:
            return None

        # 候補のinsight_id → 詳細情報のマップ
        candidate_map = {
            c.get("insight_id"): c for c in candidates
        }

        team_members = []
        all_topics: List[str] = []

        for member in members_raw:
            insight_id = member.get("insight_id", "")
            candidate = candidate_map.get(insight_id, {})
            member_topics = candidate.get("topics", [])
            all_topics.extend(member_topics)

            team_members.append({
                "user_id": insight_id,
                "display_name": member.get("display_name", "メンバー"),
                "role": member.get("role", "メンバー"),
                "avatar_url": None,
            })

        if not team_members:
            return None

        unique_topics = list(dict.fromkeys(all_topics))[:5]
        project_name = llm_result.get("project_name", "Flash Team Project")
        reason = llm_result.get(
            "reason",
            "異なる専門領域を持つメンバーによる補完的なチームです。",
        )

        proposal_id = str(uuid.uuid4())
        recommendation = {
            "id": proposal_id,
            "title": "Flash Team が結成可能です",
            "summary": (
                f"{len(team_members)}名の専門家が見つかりました。"
                "異なる視点を持つメンバーによる最適なチームを提案します。"
            ),
            "topics": unique_topics,
            "relevance_score": 90,
            "preview": reason,
            "category": "TEAM_PROPOSAL",
            "reason": reason,
            "team_members": team_members,
            "project_name": project_name,
        }

        return {
            "has_recommendations": True,
            "recommendations": [recommendation],
            "trigger_reason": "flash_team_formed",
            "display_message": "あなたに最適なチームが見つかりました",
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
