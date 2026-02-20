"""
LLM-as-a-Judge 評価基盤

各コンポーネントの出力を LLM が 1-10 で採点する。
結果は JSON で出力され、CI/CD パイプラインで閾値チェックに使用する。

サブクラスは以下を実装する:
- scoring_dimensions: 評価軸の定義
- build_judge_prompt: 評価プロンプトの構築
- run_component: コンポーネントの実行
"""
from __future__ import annotations

import json
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class EvalCase:
    """評価ケース"""
    case_id: str
    input_data: Dict[str, Any]
    actual_output: Dict[str, Any]
    expected: Dict[str, Any]
    scores: Dict[str, float] = field(default_factory=dict)
    reasoning: str = ""
    passed: bool = True


@dataclass
class EvalReport:
    """評価レポート"""
    component: str
    timestamp: str
    total_cases: int
    passed_cases: int
    average_scores: Dict[str, float]
    min_scores: Dict[str, float]
    failed_cases: List[Dict]
    details: List[Dict]

    @property
    def pass_rate(self) -> float:
        return self.passed_cases / self.total_cases if self.total_cases > 0 else 0

    def to_json(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, ensure_ascii=False, indent=2)

    def to_markdown(self) -> str:
        """Markdown 形式のサマリーを生成"""
        lines = [
            f"# Evaluation Report: {self.component}",
            f"**Timestamp:** {self.timestamp}",
            f"**Pass Rate:** {self.pass_rate:.1%} ({self.passed_cases}/{self.total_cases})",
            "",
            "## Average Scores",
        ]
        for dim, score in self.average_scores.items():
            lines.append(f"- **{dim}:** {score:.2f}")
        lines.append("")
        lines.append("## Min Scores")
        for dim, score in self.min_scores.items():
            lines.append(f"- **{dim}:** {score:.2f}")
        if self.failed_cases:
            lines.append("")
            lines.append(f"## Failed Cases ({len(self.failed_cases)})")
            for fc in self.failed_cases[:10]:
                lines.append(f"- **{fc['id']}**: {fc['scores']}")
                if fc.get("reasoning"):
                    lines.append(f"  - {fc['reasoning'][:200]}")
        return "\n".join(lines)


class BaseEvaluator(ABC):
    """
    LLM-as-a-Judge 評価器の基底クラス

    サブクラスは以下を実装する:
    - scoring_dimensions: 評価軸の定義
    - build_judge_prompt: 評価プロンプトの構築
    - run_component: コンポーネントの実行
    - _rule_based_check (任意): LLM なしのルールベース評価
    """

    def __init__(self, component_name: str, pass_threshold: float = 6.0):
        self.component_name = component_name
        self.pass_threshold = pass_threshold

    @property
    @abstractmethod
    def scoring_dimensions(self) -> List[Dict[str, str]]:
        """
        評価軸の定義。

        Returns:
            [{"name": "privacy", "description": "PII除去の完全性"}, ...]
        """

    @abstractmethod
    async def run_component(self, input_data: Dict) -> Dict:
        """対象コンポーネントを実行して出力を得る"""

    @abstractmethod
    def build_judge_prompt(
        self, input_data: Dict, output: Dict, expected: Dict
    ) -> str:
        """LLM Judge 用のプロンプトを構築"""

    def _rule_based_check(
        self, input_data: Dict, output: Dict, expected: Dict
    ) -> Tuple[Dict[str, float], str]:
        """
        LLM なしのルールベースチェック。
        サブクラスでオーバーライドして具体的なルールを実装する。
        """
        return {}, "Rule-based check not implemented"

    async def evaluate_single(
        self, case: Dict, judge_provider=None
    ) -> EvalCase:
        """1ケースを評価"""
        input_data = case["input"]
        expected = case["expected"]

        # コンポーネント実行
        try:
            actual_output = await self.run_component(input_data)
        except Exception as e:
            logger.warning(
                "Component execution failed for case %s: %s",
                case["id"], str(e),
            )
            eval_case = EvalCase(
                case_id=case["id"],
                input_data=input_data,
                actual_output={"error": str(e)},
                expected=expected,
                scores={d["name"]: 1.0 for d in self.scoring_dimensions},
                reasoning=f"Component execution failed: {e}",
                passed=False,
            )
            return eval_case

        eval_case = EvalCase(
            case_id=case["id"],
            input_data=input_data,
            actual_output=actual_output,
            expected=expected,
        )

        # LLM Judge による採点
        if judge_provider:
            scores = await self._judge_with_llm(
                judge_provider, input_data, actual_output, expected
            )
            eval_case.scores = scores.get("scores", {})
            eval_case.reasoning = scores.get("reasoning", "")
        else:
            # LLM なしのルールベース評価
            eval_case.scores, eval_case.reasoning = self._rule_based_check(
                input_data, actual_output, expected
            )

        # 全スコアが閾値以上なら passed
        if eval_case.scores:
            eval_case.passed = all(
                s >= self.pass_threshold for s in eval_case.scores.values()
            )
        else:
            eval_case.passed = False

        return eval_case

    async def evaluate_all(
        self, golden_path: Path, judge_provider=None
    ) -> EvalReport:
        """Golden Dataset 全体を評価"""
        with open(golden_path, encoding="utf-8") as f:
            dataset = json.load(f)

        cases = dataset["cases"]
        results: List[EvalCase] = []

        for case in cases:
            result = await self.evaluate_single(case, judge_provider)
            results.append(result)
            logger.info(
                "Evaluated %s: passed=%s scores=%s",
                result.case_id, result.passed, result.scores,
            )

        return self._build_report(results)

    def _build_report(self, results: List[EvalCase]) -> EvalReport:
        """評価結果からレポートを構築"""
        all_dims = set()
        for r in results:
            all_dims.update(r.scores.keys())

        avg_scores: Dict[str, float] = {}
        min_scores: Dict[str, float] = {}
        for dim in sorted(all_dims):
            values = [r.scores[dim] for r in results if dim in r.scores]
            avg_scores[dim] = sum(values) / len(values) if values else 0.0
            min_scores[dim] = min(values) if values else 0.0

        failed = [
            {
                "id": r.case_id,
                "scores": r.scores,
                "reasoning": r.reasoning,
            }
            for r in results
            if not r.passed
        ]

        return EvalReport(
            component=self.component_name,
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
            total_cases=len(results),
            passed_cases=sum(1 for r in results if r.passed),
            average_scores=avg_scores,
            min_scores=min_scores,
            failed_cases=failed,
            details=[asdict(r) for r in results],
        )

    async def _judge_with_llm(
        self, provider, input_data: Dict, output: Dict, expected: Dict
    ) -> Dict:
        """LLM に採点させる"""
        prompt = self.build_judge_prompt(input_data, output, expected)
        dims_desc = "\n".join(
            f"- {d['name']}: {d['description']}"
            for d in self.scoring_dimensions
        )
        system = (
            "あなたは AI 出力の品質を評価する専門家です。\n"
            f"以下の {len(self.scoring_dimensions)} 軸で 1-10 点で採点してください。\n\n"
            f"評価軸:\n{dims_desc}\n\n"
            "必ず以下の JSON 形式で返してください:\n"
            '{"scores": {"軸名": 点数, ...}, "reasoning": "採点理由"}\n\n'
            "注意:\n"
            "- 各スコアは整数 (1-10) で返すこと\n"
            "- reasoning は日本語で簡潔に記述すること\n"
            "- JSON 以外のテキストは含めないこと"
        )

        try:
            await provider.initialize()
            result = await provider.generate_json(
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
            )
            # スコアが全軸分あることを検証
            scores = result.get("scores", {})
            for dim in self.scoring_dimensions:
                if dim["name"] not in scores:
                    scores[dim["name"]] = 1.0  # 欠落した軸は最低点
            result["scores"] = scores
            return result
        except Exception as e:
            logger.warning("LLM judge failed: %s", str(e))
            return {
                "scores": {d["name"]: 1.0 for d in self.scoring_dimensions},
                "reasoning": f"LLM judge error: {e}",
            }
