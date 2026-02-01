"""
MINDYARD - Sharing Broker
Layer 2: 生成されたインサイトをユーザーに提示し、共有の許諾を得る
"""
import json
from typing import Dict, Optional, Tuple
from datetime import datetime, timezone

from openai import AsyncOpenAI

from app.core.config import settings


class SharingBroker:
    """
    Sharing Broker (共有仲介人)

    機能:
    - 共有価値スコアの算出
    - 共有提案の生成
    - ユーザーの承認処理
    """

    def __init__(self):
        self.client = AsyncOpenAI(api_key=settings.openai_api_key) if settings.openai_api_key else None
        self.threshold = settings.sharing_threshold_score

    async def evaluate_sharing_value(self, insight: Dict) -> Dict:
        """
        インサイトの共有価値を評価

        Returns:
            {
                "sharing_value_score": float (0-100),
                "novelty_score": float (0-100),
                "generality_score": float (0-100),
                "should_propose": bool,
                "reasoning": str
            }
        """
        if not self.client:
            return self._fallback_evaluate(insight)

        prompt = self._build_evaluation_prompt(insight)

        try:
            response = await self.client.chat.completions.create(
                model=settings.openai_model,
                messages=[
                    {"role": "system", "content": self._get_evaluation_system_prompt()},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.3,
            )

            result = json.loads(response.choices[0].message.content)
            return self._parse_evaluation_result(result)

        except Exception as e:
            return self._fallback_evaluate(insight)

    def _get_evaluation_system_prompt(self) -> str:
        return """あなたはMINDYARDの共有価値評価エンジンです。
インサイトカードが組織内で共有される価値があるかを評価してください。

評価基準:
1. 新規性 (novelty_score): 他では得られない独自の知見か
2. 汎用性 (generality_score): 多くの人に適用可能か
3. 総合スコア (sharing_value_score): 上記を総合した共有価値

スコアは0-100で評価してください。
70点以上で共有を提案します。

必ず以下のJSON形式で応答:
{
    "sharing_value_score": 75,
    "novelty_score": 80,
    "generality_score": 70,
    "should_propose": true,
    "reasoning": "評価理由の説明"
}"""

    def _build_evaluation_prompt(self, insight: Dict) -> str:
        return f"""以下のインサイトカードの共有価値を評価してください:

タイトル: {insight.get('title', '')}
背景: {insight.get('context', '')}
課題: {insight.get('problem', '')}
解決策/結果: {insight.get('solution', '')}
要約: {insight.get('summary', '')}
トピック: {', '.join(insight.get('topics', []))}
タグ: {', '.join(insight.get('tags', []))}

この知見は組織内で共有する価値がありますか？"""

    def _parse_evaluation_result(self, result: Dict) -> Dict:
        """評価結果のパース"""
        sharing_score = float(result.get("sharing_value_score", 0))
        novelty_score = float(result.get("novelty_score", 0))
        generality_score = float(result.get("generality_score", 0))

        return {
            "sharing_value_score": sharing_score,
            "novelty_score": novelty_score,
            "generality_score": generality_score,
            "should_propose": sharing_score >= self.threshold,
            "reasoning": result.get("reasoning", ""),
        }

    def _fallback_evaluate(self, insight: Dict) -> Dict:
        """LLMが利用できない場合のフォールバック評価"""
        # 簡易スコアリング
        score = 50  # ベーススコア

        # コンテンツの充実度で加点
        if insight.get("context"):
            score += 10
        if insight.get("problem"):
            score += 10
        if insight.get("solution"):
            score += 15
        if len(insight.get("topics", [])) > 0:
            score += 5
        if len(insight.get("summary", "")) > 50:
            score += 10

        score = min(score, 100)

        return {
            "sharing_value_score": score,
            "novelty_score": score,
            "generality_score": score,
            "should_propose": score >= self.threshold,
            "reasoning": "自動評価によるスコアリング",
        }

    def generate_proposal_message(self, insight: Dict, score: float) -> str:
        """共有提案メッセージを生成"""
        base_message = "あなたのこの経験は、チームの役に立つ可能性があります。"

        if score >= 90:
            return f"{base_message}特に価値の高い知見だと思います。ぜひ共有しませんか？"
        elif score >= 80:
            return f"{base_message}多くの人に参考になりそうです。この形式で共有しますか？"
        else:
            return f"{base_message}この形式で共有しますか？"


# シングルトンインスタンス
sharing_broker = SharingBroker()
