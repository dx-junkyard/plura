"""
PLURA - Policy Weaver
Layer 3: Flash Team 解散時の非構造化ログから
「技術選定・非機能要件のジレンマ」を抽出し、
再利用可能なガバナンスルール（Governance as Code）として定着させる。

設計思想:
  - 二段階制度化 (Heuristic先行): 初期は SUGGEST として運用
  - TTL 新陳代謝: 30日の再評価期限を付与
  - Override 駆動: 逸脱理由を蓄積してルール改善に活かす
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from app.core.llm import extract_json_from_text, llm_manager
from app.core.llm_provider import LLMUsageRole
from app.models.policy import DEFAULT_TTL_DAYS, EnforcementLevel
from app.schemas.policy import BoundaryConditions, ExtractedPolicy, ExtractionResult

logger = logging.getLogger(__name__)


EXTRACTION_SYSTEM_PROMPT = """\
あなたは「Policy Weaver（ガバナンス・アーキテクト）」です。
プロジェクトチームの非構造化ログ（チャット履歴・議事録・コミットメッセージなど）を分析し、
チームが経験した**技術選定のジレンマ**や**非機能要件のトレードオフ**を抽出する専門家です。

## あなたの使命
入力されたログから、次のチームが再利用できる「暗黙知のルール」を発見してください。
日常会話・雑談・単なる進捗報告は無視し、**意思決定の痕跡**のみに注目してください。

## 抽出対象の例
- 「パフォーマンスと開発速度のトレードオフでXを選んだ」
- 「セキュリティ要件のためYの代わりにZを採用した」
- 「短期的にはAだがスケーラビリティを考慮してBにした」
- 「ユーザーの利便性 vs. データの一貫性で悩んだ末にCの方針にした」

## 出力ルール
- 抽出可能なジレンマが**存在する場合**、以下のJSON形式で出力してください。
- 抽出可能なジレンマが**存在しない場合**、`{"policies": []}` のみを出力してください。
- 最大5件まで。質を優先し、曖昧なものは含めないでください。

## JSON出力フォーマット
```json
{
  "policies": [
    {
      "dilemma_context": "チームが直面したトレードオフの状況を具体的に説明（2-3文）",
      "principle": "この経験から導かれるルールを1文で簡潔に記述",
      "boundary_conditions": {
        "applies_when": ["この原則が適用される条件1", "条件2"],
        "except_when": ["この原則の例外条件1"]
      }
    }
  ]
}
```

必ずJSONのみを出力してください。説明文や前置きは不要です。\
"""


class PolicyWeaver:
    """
    Policy Weaver サービス

    プロジェクトの非構造化ログからガバナンスルールを抽出する。
    """

    async def extract_policies(
        self,
        logs: List[str],
        project_context: Optional[str] = None,
    ) -> ExtractionResult:
        """
        非構造化ログからポリシーを抽出する。

        Args:
            logs: プロジェクトの非構造化ログ（チャット履歴等）のリスト
            project_context: プロジェクトの追加コンテキスト（名前・説明等）

        Returns:
            ExtractionResult: 抽出されたポリシーのリスト
        """
        if not logs:
            logger.info("No logs provided for policy extraction")
            return ExtractionResult(policies=[])

        # ログを結合（長すぎる場合は先頭を切り詰め）
        combined_logs = "\n---\n".join(logs)
        max_chars = 15000  # LLMのコンテキスト制約を考慮
        if len(combined_logs) > max_chars:
            combined_logs = combined_logs[-max_chars:]
            logger.info(
                "Truncated logs to last %d chars for policy extraction", max_chars
            )

        user_message = self._build_user_message(combined_logs, project_context)

        try:
            provider = llm_manager.get_client(LLMUsageRole.BALANCED)
            await provider.initialize()

            response = await provider.generate_text(
                messages=[
                    {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                temperature=0.2,
            )

            parsed = extract_json_from_text(response.content)
            if not parsed:
                logger.warning("Failed to parse LLM response as JSON: %s", response.content[:200])
                return ExtractionResult(policies=[])

            policies_raw = parsed.get("policies", [])
            policies = []
            for item in policies_raw:
                try:
                    bc = item.get("boundary_conditions", {})
                    policies.append(
                        ExtractedPolicy(
                            dilemma_context=item["dilemma_context"],
                            principle=item["principle"],
                            boundary_conditions=BoundaryConditions(
                                applies_when=bc.get("applies_when", []),
                                except_when=bc.get("except_when", []),
                            ),
                        )
                    )
                except (KeyError, TypeError) as e:
                    logger.warning("Skipping malformed policy item: %s", e)
                    continue

            logger.info("Extracted %d policies from logs", len(policies))
            return ExtractionResult(policies=policies)

        except Exception as e:
            logger.error("Policy extraction failed: %s", e, exc_info=True)
            return ExtractionResult(policies=[])

    def _build_user_message(
        self,
        combined_logs: str,
        project_context: Optional[str],
    ) -> str:
        """LLM に送るユーザーメッセージを組み立てる"""
        parts = []
        if project_context:
            parts.append(f"## プロジェクト情報\n{project_context}\n")
        parts.append(f"## プロジェクトログ\n{combined_logs}")
        return "\n".join(parts)

    @staticmethod
    def compute_ttl_expiry(days: int = DEFAULT_TTL_DAYS) -> datetime:
        """TTL 期限を算出する"""
        return datetime.now(timezone.utc) + timedelta(days=days)


# シングルトンインスタンス
policy_weaver = PolicyWeaver()
