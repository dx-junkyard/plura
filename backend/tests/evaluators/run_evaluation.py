"""
LLM-as-a-Judge 評価 CLI

Usage:
  # ルールベース評価（LLM なし）
  python -m tests.evaluators.run_evaluation --component privacy_sanitizer
  python -m tests.evaluators.run_evaluation --component intent_router

  # 全コンポーネント評価
  python -m tests.evaluators.run_evaluation --all

  # LLM Judge を使用した評価
  python -m tests.evaluators.run_evaluation --component privacy_sanitizer --use-llm

  # カスタム閾値
  python -m tests.evaluators.run_evaluation --all --threshold 7.0

  # CI/CD 用: 失敗時に非ゼロ終了コード
  python -m tests.evaluators.run_evaluation --all --ci
"""
from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from tests.evaluators.base_evaluator import BaseEvaluator, EvalReport

# Evaluator の登録: (モジュールパス, クラス名)
EVALUATOR_MAP: Dict[str, Tuple[str, str]] = {
    "intent_router": (
        "tests.evaluators.intent_evaluator",
        "IntentEvaluator",
    ),
    "privacy_sanitizer": (
        "tests.evaluators.privacy_evaluator",
        "PrivacyEvaluator",
    ),
    "insight_distiller": (
        "tests.evaluators.insight_evaluator",
        "InsightEvaluator",
    ),
    "serendipity_matcher": (
        "tests.evaluators.serendipity_evaluator",
        "SerendipityEvaluator",
    ),
}

GOLDEN_DIR = Path(__file__).parent.parent / "golden_datasets"
REPORTS_DIR = Path(__file__).parent.parent / "eval_reports"


def _load_evaluator(component: str) -> BaseEvaluator:
    """コンポーネント名から Evaluator インスタンスを生成"""
    module_path, class_name = EVALUATOR_MAP[component]
    mod = importlib.import_module(module_path)
    evaluator_cls = getattr(mod, class_name)
    return evaluator_cls()


def _get_judge_provider(use_llm: bool):
    """LLM Judge 用のプロバイダーを取得"""
    if not use_llm:
        return None
    try:
        from app.core.llm import llm_manager
        from app.core.llm_provider import LLMUsageRole
        return llm_manager.get_client(LLMUsageRole.BALANCED)
    except Exception as e:
        print(f"Warning: Failed to get LLM provider: {e}")
        print("Falling back to rule-based evaluation.")
        return None


def _append_failures(component: str, failures: List[Dict]) -> None:
    """失敗ケースを failure_cases.json に蓄積（Phase 3 向けデータ供給）"""
    failure_path = Path(__file__).parent.parent / "optimization" / "failure_cases.json"
    failure_path.parent.mkdir(exist_ok=True)

    existing: List[Dict] = []
    if failure_path.exists():
        try:
            with open(failure_path, encoding="utf-8") as f:
                existing = json.load(f)
        except (json.JSONDecodeError, IOError):
            existing = []

    for case in failures:
        existing.append({
            "component": component,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            **case,
        })

    with open(failure_path, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)


def _print_report(report: EvalReport) -> None:
    """レポートをコンソールに出力"""
    print(f"\n{'=' * 60}")
    print(f"Component: {report.component}")
    print(f"Pass Rate: {report.pass_rate:.1%} ({report.passed_cases}/{report.total_cases})")
    print(f"Average Scores:")
    for dim, score in report.average_scores.items():
        status = "PASS" if score >= 6.0 else "FAIL"
        print(f"  {dim}: {score:.2f} [{status}]")
    print(f"Min Scores:")
    for dim, score in report.min_scores.items():
        print(f"  {dim}: {score:.2f}")
    if report.failed_cases:
        print(f"\nFailed Cases ({len(report.failed_cases)}):")
        for fc in report.failed_cases[:5]:
            print(f"  - {fc['id']}: scores={fc['scores']}")
            if fc.get("reasoning"):
                print(f"    reason: {fc['reasoning'][:120]}")
        if len(report.failed_cases) > 5:
            print(f"  ... and {len(report.failed_cases) - 5} more")
    print(f"{'=' * 60}\n")


async def run_eval(
    component: str,
    use_llm: bool = False,
    threshold: Optional[float] = None,
) -> EvalReport:
    """単一コンポーネントの評価を実行"""
    evaluator = _load_evaluator(component)
    if threshold is not None:
        evaluator.pass_threshold = threshold

    golden_path = GOLDEN_DIR / f"{component}.json"
    if not golden_path.exists():
        print(f"Error: Golden dataset not found: {golden_path}")
        sys.exit(1)

    judge = _get_judge_provider(use_llm)
    report = await evaluator.evaluate_all(golden_path, judge)

    # レポート保存
    REPORTS_DIR.mkdir(exist_ok=True)
    report_path = REPORTS_DIR / f"{component}_report.json"
    report.to_json(report_path)
    print(f"Report saved: {report_path}")

    # コンソール出力
    _print_report(report)

    # 失敗ケースを Phase 3 用に蓄積
    if report.failed_cases:
        _append_failures(component, report.failed_cases)

    return report


async def run_all(
    use_llm: bool = False,
    threshold: Optional[float] = None,
) -> List[EvalReport]:
    """全コンポーネントの評価を実行"""
    reports = []
    for component in EVALUATOR_MAP:
        golden_path = GOLDEN_DIR / f"{component}.json"
        if not golden_path.exists():
            print(f"Skipping {component}: Golden dataset not found")
            continue
        report = await run_eval(component, use_llm, threshold)
        reports.append(report)
    return reports


def main() -> None:
    parser = argparse.ArgumentParser(
        description="PLURA LLM-as-a-Judge Evaluation Runner"
    )
    parser.add_argument(
        "--component",
        choices=list(EVALUATOR_MAP.keys()),
        help="評価対象コンポーネント",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="全コンポーネントを評価",
    )
    parser.add_argument(
        "--use-llm",
        action="store_true",
        help="LLM Judge を使用（API キーが必要）",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=None,
        help="合格閾値（デフォルト: コンポーネントごとの設定値）",
    )
    parser.add_argument(
        "--ci",
        action="store_true",
        help="CI モード: pass_rate < 70%% の場合に非ゼロ終了コード",
    )
    args = parser.parse_args()

    if not args.all and not args.component:
        parser.print_help()
        sys.exit(1)

    if args.all:
        reports = asyncio.run(run_all(args.use_llm, args.threshold))
    else:
        report = asyncio.run(run_eval(args.component, args.use_llm, args.threshold))
        reports = [report]

    # CI モード: 品質ゲート
    if args.ci:
        failed_components = []
        for report in reports:
            if report.pass_rate < 0.70:
                failed_components.append(
                    f"{report.component}: {report.pass_rate:.1%}"
                )
        if failed_components:
            print("\nQuality Gate FAILED:")
            for fc in failed_components:
                print(f"  - {fc}")
            sys.exit(1)
        else:
            print("\nQuality Gate PASSED: All components above 70% pass rate.")


if __name__ == "__main__":
    main()
