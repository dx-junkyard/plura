"""
MINDYARD - Sharing Broker
Layer 2: 生成されたインサイトをユーザーに提示し、共有の許諾を得る

バランスの取れた評価が必要なため、BALANCEDモデルを使用。
"""
from typing import Dict, Optional
from datetime import datetime, timezone

from app.core.config import settings
from app.core.llm import llm_manager
from app.core.llm_provider import LLMProvider, LLMUsageRole

import logging
logger = logging.getLogger(__name__)

class SharingBroker:
    """
    Sharing Broker (共有仲介人)

    機能:
    - 共有価値スコアの算出
    - 共有提案の生成
    - ユーザーの承認処理

    BALANCEDモデルを使用してバランスの取れた評価を行う。
    """

    def __init__(self):
        self._provider: Optional[LLMProvider] = None
        self.threshold = settings.sharing_threshold_score

    def _get_provider(self) -> Optional[LLMProvider]:
        """LLMプロバイダーを取得（遅延初期化）"""
        if self._provider is None:
            try:
                self._provider = llm_manager.get_client(LLMUsageRole.BALANCED)
            except Exception:
                pass
        return self._provider

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
        provider = self._get_provider()
        if not provider:
            logger.warning(f"[SharingBroker] No provider available for role: {role}")
            return self._fallback_evaluate(insight)

        prompt = self._build_evaluation_prompt(insight)

        try:
            await provider.initialize()
            result = await provider.generate_json(
                messages=[
                    {"role": "system", "content": self._get_evaluation_system_prompt()},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
            )

            return self._parse_evaluation_result(result)

        except Exception as e:
            logger.error(
                f"[SharingBroker] LLM Error during sharing evaluation!\n"
                f"  - Model Info: {model_info}\n"
                f"  - Role: {role}\n"
                f"  - Error: {str(e)}", 
                exc_info=True
            )
            return self._fallback_evaluate(insight)

    def _get_evaluation_system_prompt(self) -> str:
        return """あなたはMINDYARDの共有価値評価エンジンです。
インサイトカードが組織内で共有される価値があるかを**厳格に**評価してください。

## 評価基準（5軸）
1. 新規性 (novelty_score): 他では得られない独自の知見か
2. 汎用性 (generality_score): 多くの人に適用可能か
3. 実用性 (practicality_score): 読んだ人がすぐ行動に移せる具体的な内容か
4. 具体性 (specificity_score): 数値・ツール名・手順など具体的な要素があるか
5. 総合スコア (sharing_value_score): 上記を総合した共有価値

## 厳格な評価ルール
- 「解決策/結果」が空 or 曖昧（「気をつける」「改善する」等）→ 総合スコア50以下
- 「背景」「課題」「解決策」のうち2つ以上が空 → 総合スコア40以下
- タイトルが抽象的で検索に役立たない → 減点
- 当たり前の内容（「コミュニケーションは大事」等）→ 新規性20以下
- 80点以上は「読んだ人が明日から使える具体的な知見」にのみ付与

スコアは0-100で評価してください。

必ず以下のJSON形式で応答:
{
    "sharing_value_score": 75,
    "novelty_score": 80,
    "generality_score": 70,
    "practicality_score": 65,
    "specificity_score": 70,
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
        sharing_score = float(result.get("sharing_value_score", 0) or 0)
        novelty_score = float(result.get("novelty_score", 0) or 0)
        generality_score = float(result.get("generality_score", 0) or 0)
        reasoning = str(result.get("reasoning", "") or "").strip()
        if not reasoning:
            reasoning = "評価理由の出力なし"

        return {
            "sharing_value_score": sharing_score,
            "novelty_score": novelty_score,
            "generality_score": generality_score,
            "should_propose": sharing_score >= self.threshold,
            "reasoning": reasoning,
        }

    def _fallback_evaluate(self, insight: Dict) -> Dict:
        """
        LLMが利用できない場合のフォールバック評価。
        「存在するか」ではなく「中身に質があるか」で判定する。
        """
        score = 30  # ベーススコア（低めに設定し、質で加点）

        context = (insight.get("context") or "").strip()
        problem = (insight.get("problem") or "").strip()
        solution = (insight.get("solution") or "").strip()
        summary = (insight.get("summary") or "").strip()
        topics = insight.get("topics") or []

        # ── 必須条件: solution が充実していること ──
        # solution がない or 短すぎる → 推奨ラインに届かない
        if len(solution) >= 50:
            score += 25  # 具体的な解決策がある
        elif len(solution) >= 20:
            score += 10  # 短いが存在する
        # solution が空 or 極短 → 加点なし（推奨80に届かない設計）

        # ── context + problem の充実度 ──
        if len(context) >= 30:
            score += 10
        if len(problem) >= 20:
            score += 10

        # ── summary の充実度 ──
        if len(summary) >= 80:
            score += 10
        elif len(summary) >= 40:
            score += 5

        # ── トピックの有無 ──
        if len(topics) >= 2:
            score += 5

        # ── ペナルティ: 3フィールド中2つ以上が空 ──
        empty_count = sum(1 for f in [context, problem, solution] if len(f) < 10)
        if empty_count >= 2:
            score = min(score, 40)  # 上限40に制限

        score = min(score, 100)

        return {
            "sharing_value_score": score,
            "novelty_score": score,
            "generality_score": score,
            "should_propose": score >= self.threshold,
            "reasoning": "自動評価（LLM未使用）: コンテンツ充実度に基づくスコアリング",
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
