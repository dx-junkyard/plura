---
name: plura-self-optimization
description: |
  PLURA の「3階建て構造(Private / Gateway / Public)」の各コンポーネントに対して、
  独立テスト・LLM-as-a-Judge 自動評価・プロンプト自己最適化を実施するためのスキル。
  テスト作成、Golden Dataset 構築、評価エージェント実装、プロンプト A/B テストを支援する。
  使用タイミング: テスト追加、品質評価、プロンプト改善、CI パイプライン構築時。
---

# PLURA Self-Optimization Skill

PLURA バックエンドの LLM 依存コンポーネントに対して、**独立テスト → 自動評価 → プロンプト最適化** のサイクルを構築・実行するためのガイド。

---

## 1. アーキテクチャ理解（前提知識）

作業前に必ず以下のコンポーネントマップを把握すること。

```
Layer 1 (Private)     Layer 2 (Gateway)           Layer 3 (Public)
─────────────────     ──────────────────────      ──────────────────
IntentRouter          PrivacySanitizer            SerendipityMatcher
ContextAnalyzer       InsightDistiller            KnowledgeStore
ConversationAgent     SharingBroker
SituationRouter       StructuralAnalyzer
```

### 対象コンポーネントと評価指標

| Component | File | 評価観点 | モデルTier |
|-----------|------|----------|-----------|
| `IntentRouter` | `services/layer1/intent_router.py` | 意図分類正解率, Probe発動の適切性 | FAST |
| `ContextAnalyzer` | `services/layer1/context_analyzer.py` | intent/emotion/topics 抽出精度 | FAST |
| `PrivacySanitizer` | `services/layer2/privacy_sanitizer.py` | PII除去率(Recall), 文脈維持率 | BALANCED |
| `InsightDistiller` | `services/layer2/insight_distiller.py` | 構造化品質, not_suitable判定精度 | BALANCED |
| `SharingBroker` | `services/layer2/sharing_broker.py` | スコアリング妥当性, 閾値判定精度 | BALANCED |
| `StructuralAnalyzer` | `services/layer2/structural_analyzer.py` | 関係性判定, probing_question品質 | DEEP |
| `SerendipityMatcher` | `services/layer3/serendipity_matcher.py` | チーム補完性, Synergy Score | BALANCED |

---

## 2. ディレクトリ構造

以下の構造を `backend/tests/` 配下に構築する。

```
backend/tests/
├── conftest.py                    # 共通フィクスチャ（LLMモック等）
├── golden_datasets/               # Phase 1: 評価用データセット
│   ├── README.md
│   ├── intent_router.json
│   ├── context_analyzer.json
│   ├── privacy_sanitizer.json
│   ├── insight_distiller.json
│   ├── sharing_broker.json
│   ├── structural_analyzer.json
│   └── serendipity_matcher.json
├── unit/                          # Phase 1: 独立単体テスト
│   ├── test_intent_router.py
│   ├── test_context_analyzer.py
│   ├── test_privacy_sanitizer.py
│   ├── test_insight_distiller.py
│   ├── test_sharing_broker.py
│   ├── test_structural_analyzer.py
│   └── test_serendipity_matcher.py
├── evaluators/                    # Phase 2: LLM-as-a-Judge
│   ├── __init__.py
│   ├── base_evaluator.py          # 評価基盤クラス
│   ├── privacy_evaluator.py
│   ├── insight_evaluator.py
│   ├── intent_evaluator.py
│   ├── serendipity_evaluator.py
│   └── run_evaluation.py          # CLI エントリポイント
├── optimization/                  # Phase 3: プロンプト自己最適化
│   ├── failure_cases.json         # 自動蓄積される失敗ケース
│   ├── prompt_optimizer.py        # プロンプト改善エージェント
│   └── ab_test_runner.py          # A/B テスト実行
└── integration/                   # 結合テスト（Phase 1 の補完）
    └── test_layer2_pipeline.py    # Sanitizer→Distiller→Broker の結合
```

---

## 3. Phase 1: 独立テスト環境と Golden Dataset

### 3.1 Golden Dataset のフォーマット

各コンポーネント用の JSON ファイルは以下の形式で作成する。

```json
{
  "component": "IntentRouter",
  "version": "1.0",
  "description": "IntentRouter の意図分類テストケース",
  "cases": [
    {
      "id": "IR-001",
      "input": {
        "text": "眠い",
        "prev_context": null
      },
      "expected": {
        "primary_intent": "state_share",
        "min_confidence": 0.5
      },
      "tags": ["state", "short_input"],
      "difficulty": "easy"
    },
    {
      "id": "IR-002",
      "input": {
        "text": "プロジェクトの進め方について、チームメンバーとのコミュニケーションがうまくいかなくて困っている",
        "prev_context": null
      },
      "expected": {
        "primary_intent": "deep_dive",
        "min_confidence": 0.6,
        "should_not_be": ["chat", "state_share"]
      },
      "tags": ["problem_solving", "long_input"],
      "difficulty": "medium"
    }
  ]
}
```

### 3.2 各コンポーネント用 Golden Dataset の設計指針

**IntentRouter** (最低20件):
- 各 intent (chat, empathy, knowledge, deep_dive, brainstorm, state_share) に最低3件
- 曖昧なケース（2つの intent が競合）を5件以上
- 短い入力（1-5文字）を3件

**ContextAnalyzer** (最低20件):
- ポジティブ/ネガティブ/中立 各5件以上
- deep_research トリガーキーワードを含むケース3件
- state と vent の境界ケース5件

**PrivacySanitizer** (最低20件):
- 電話番号・メールアドレスを含むケース各3件
- 人名（姓＋敬称）を含むケース5件
- 企業名・プロジェクト名を含むケース5件
- PII が含まれないケース3件（false positive 検証）

**InsightDistiller** (最低20件):
- 質の高い知見になるべき入力10件
- not_suitable と判定すべき入力10件（雑談、短文、テスト投稿等）

**SharingBroker** (最低20件):
- スコア80以上になるべき高品質インサイト5件
- スコア40以下になるべき低品質インサイト5件
- 境界（60-80）のケース10件

**SerendipityMatcher** (最低10件):
- 補完的なチームが組めるべき候補セット5件
- チーム不成立とすべき候補セット5件

### 3.3 単体テストの書き方

LLM 依存を断ち切るため、**2層テスト**を実施する。

```python
# tests/unit/test_intent_router.py
import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app.services.layer1.intent_router import IntentRouter
from app.schemas.conversation import ConversationIntent

GOLDEN_DATA = Path(__file__).parent.parent / "golden_datasets" / "intent_router.json"


@pytest.fixture
def golden_cases():
    """Golden Dataset を読み込む"""
    with open(GOLDEN_DATA) as f:
        data = json.load(f)
    return data["cases"]


@pytest.fixture
def router():
    return IntentRouter()


class TestIntentRouterFallback:
    """Layer A: LLM なしのフォールバック（キーワードベース）テスト"""

    def test_state_share_keywords(self, router):
        result = router._fallback_classify("眠い")
        assert result["primary_intent"] == ConversationIntent.STATE_SHARE

    def test_empathy_keywords(self, router):
        result = router._fallback_classify("つらい、もう限界だ")
        assert result["primary_intent"] == ConversationIntent.EMPATHY

    @pytest.mark.parametrize("case_id,case", [
        (c["id"], c) for c in json.load(open(GOLDEN_DATA))["cases"]
        if c.get("difficulty") == "easy"
    ])
    def test_golden_easy_cases_fallback(self, router, case_id, case):
        """Golden Dataset の easy ケースはフォールバックでも正解すべき"""
        result = router._fallback_classify(case["input"]["text"])
        expected_intent = ConversationIntent(case["expected"]["primary_intent"])
        assert result["primary_intent"] == expected_intent, (
            f"Case {case_id}: expected {expected_intent}, got {result['primary_intent']}"
        )


class TestIntentRouterWithLLM:
    """Layer B: LLM ありのテスト（モック or 実 API）"""

    @pytest.mark.asyncio
    async def test_with_mock_llm(self, router):
        """LLM レスポンスをモックしてパース処理を検証"""
        mock_response = {
            "primary_intent": "deep_dive",
            "primary_confidence": 0.85,
            "secondary_intent": "empathy",
            "secondary_confidence": 0.10,
            "needs_probing": False,
            "previous_evaluation": "none",
            "reasoning": "問題解決を求めている",
        }
        with patch.object(router, "_get_provider") as mock_provider:
            provider = AsyncMock()
            provider.generate_json = AsyncMock(return_value=mock_response)
            provider.initialize = AsyncMock()
            mock_provider.return_value = provider

            result = await router.classify("プロジェクトの進め方で困っている")
            assert result["primary_intent"] == ConversationIntent.DEEP_DIVE
            assert result["confidence"] >= 0.8

    @pytest.mark.skipif(
        not _has_llm_key(), reason="LLM API key not set"
    )
    @pytest.mark.asyncio
    async def test_golden_with_real_llm(self, router, golden_cases):
        """実 LLM で Golden Dataset を実行（CI では skip）"""
        passed = 0
        failed = []
        for case in golden_cases:
            result = await router.classify(
                case["input"]["text"],
                prev_context=case["input"].get("prev_context"),
            )
            expected = ConversationIntent(case["expected"]["primary_intent"])
            if result["primary_intent"] == expected:
                passed += 1
            else:
                failed.append({
                    "id": case["id"],
                    "expected": expected.value,
                    "got": result["primary_intent"].value,
                })
        accuracy = passed / len(golden_cases)
        print(f"IntentRouter accuracy: {accuracy:.1%} ({passed}/{len(golden_cases)})")
        assert accuracy >= 0.7, f"Accuracy {accuracy:.1%} below 70%. Failed: {failed}"


def _has_llm_key():
    """LLM API キーが設定されているか"""
    from app.core.config import settings
    return settings.is_openai_available() or settings.is_google_genai_available()
```

### 3.4 共通フィクスチャ（conftest.py）

```python
# tests/conftest.py
import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.fixture
def mock_llm_provider():
    """LLM プロバイダーのモック"""
    provider = AsyncMock()
    provider.initialize = AsyncMock()
    provider.generate_json = AsyncMock(return_value={})
    provider.generate_text = AsyncMock(return_value=MagicMock(content=""))
    provider.get_model_info = MagicMock(return_value={
        "provider": "mock", "model": "mock-model", "is_reasoning": False
    })
    return provider


@pytest.fixture
def mock_embedding_provider():
    """Embedding プロバイダーのモック"""
    provider = AsyncMock()
    provider.initialize = AsyncMock()
    provider.embed_text = AsyncMock(return_value=[0.1] * 1536)
    provider.embed_texts = AsyncMock(return_value=[[0.1] * 1536])
    provider.vector_size = 1536
    return provider
```

---

## 4. Phase 2: LLM-as-a-Judge 自動評価

### 4.1 評価基盤クラス

```python
# tests/evaluators/base_evaluator.py
"""
LLM-as-a-Judge 評価基盤

各コンポーネントの出力を LLM が 1-10 で採点する。
結果は JSON で出力され、CI/CD パイプラインで閾値チェックに使用する。
"""
import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional


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

    def to_json(self, path: Path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, ensure_ascii=False, indent=2)


class BaseEvaluator(ABC):
    """
    LLM-as-a-Judge 評価器の基底クラス

    サブクラスは以下を実装する:
    - scoring_dimensions: 評価軸の定義
    - build_judge_prompt: 評価プロンプトの構築
    - run_component: コンポーネントの実行
    """

    def __init__(self, component_name: str, pass_threshold: float = 6.0):
        self.component_name = component_name
        self.pass_threshold = pass_threshold

    @property
    @abstractmethod
    def scoring_dimensions(self) -> List[Dict[str, str]]:
        """評価軸: [{"name": "privacy", "description": "PII除去の完全性"}]"""
        pass

    @abstractmethod
    async def run_component(self, input_data: Dict) -> Dict:
        """対象コンポーネントを実行して出力を得る"""
        pass

    @abstractmethod
    def build_judge_prompt(
        self, input_data: Dict, output: Dict, expected: Dict
    ) -> str:
        """LLM Judge 用のプロンプトを構築"""
        pass

    async def evaluate_single(
        self, case: Dict, judge_provider=None
    ) -> EvalCase:
        """1ケースを評価"""
        input_data = case["input"]
        expected = case["expected"]

        # コンポーネント実行
        actual_output = await self.run_component(input_data)

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
            # 全スコアが閾値以上なら passed
            eval_case.passed = all(
                s >= self.pass_threshold
                for s in eval_case.scores.values()
            )
        else:
            # LLM なしのルールベース評価
            eval_case.scores, eval_case.reasoning = self._rule_based_check(
                actual_output, expected
            )
            eval_case.passed = all(
                s >= self.pass_threshold
                for s in eval_case.scores.values()
            )

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

        # 集計
        all_dims = set()
        for r in results:
            all_dims.update(r.scores.keys())

        avg_scores = {}
        min_scores = {}
        for dim in all_dims:
            values = [r.scores[dim] for r in results if dim in r.scores]
            avg_scores[dim] = sum(values) / len(values) if values else 0
            min_scores[dim] = min(values) if values else 0

        failed = [
            {"id": r.case_id, "scores": r.scores, "reasoning": r.reasoning}
            for r in results if not r.passed
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
        self, provider, input_data, output, expected
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
            f"{dims_desc}\n\n"
            "必ず JSON で返してください:\n"
            '{"scores": {"軸名": 点数, ...}, "reasoning": "採点理由"}'
        )
        await provider.initialize()
        result = await provider.generate_json(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
        )
        return result

    def _rule_based_check(self, output, expected) -> tuple:
        """LLM なしのルールベースチェック（サブクラスでオーバーライド可）"""
        return {}, "Rule-based check not implemented"
```

### 4.2 PrivacySanitizer 評価器の例

```python
# tests/evaluators/privacy_evaluator.py
from typing import Dict, List
from tests.evaluators.base_evaluator import BaseEvaluator


class PrivacyEvaluator(BaseEvaluator):
    def __init__(self):
        super().__init__("PrivacySanitizer", pass_threshold=7.0)

    @property
    def scoring_dimensions(self) -> List[Dict[str, str]]:
        return [
            {"name": "pii_removal", "description": "個人特定情報(氏名, 電話, メール等)が完全に除去されているか"},
            {"name": "context_preservation", "description": "匿名化後も元の文脈・意味が保持されているか"},
            {"name": "naturalness", "description": "匿名化後の文が自然な日本語として読めるか"},
        ]

    async def run_component(self, input_data: Dict) -> Dict:
        from app.services.layer2.privacy_sanitizer import privacy_sanitizer
        content = input_data["text"]
        sanitized, metadata = await privacy_sanitizer.sanitize(content)
        return {"sanitized_text": sanitized, "metadata": metadata}

    def build_judge_prompt(self, input_data, output, expected) -> str:
        return (
            f"## 元のテキスト\n{input_data['text']}\n\n"
            f"## 匿名化後のテキスト\n{output['sanitized_text']}\n\n"
            f"## 期待される置換\n{expected.get('expected_replacements', '指定なし')}\n\n"
            "上記の匿名化結果を評価してください。"
        )

    def _rule_based_check(self, output, expected):
        """ルールベースの PII チェック"""
        import re
        text = output.get("sanitized_text", "")
        scores = {}
        reasons = []

        # メールアドレスの残存チェック
        emails = re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", text)
        # 電話番号の残存チェック
        phones = re.findall(r"0\d{1,4}-?\d{1,4}-?\d{3,4}", text)

        pii_found = len(emails) + len(phones)
        if pii_found == 0:
            scores["pii_removal"] = 10
        else:
            scores["pii_removal"] = max(1, 10 - pii_found * 3)
            reasons.append(f"PII残存: emails={len(emails)}, phones={len(phones)}")

        # 文脈維持は簡易チェック（テキスト長の比率）
        original_len = len(expected.get("original_text", "a"))
        sanitized_len = len(text)
        ratio = sanitized_len / max(original_len, 1)
        if 0.5 <= ratio <= 1.5:
            scores["context_preservation"] = 8
        else:
            scores["context_preservation"] = 5
            reasons.append(f"長さ比率: {ratio:.2f}")

        scores["naturalness"] = 7  # ルールベースでは固定

        return scores, "; ".join(reasons) if reasons else "OK"
```

### 4.3 評価 CLI

```python
# tests/evaluators/run_evaluation.py
"""
Usage:
  python -m tests.evaluators.run_evaluation --component privacy_sanitizer
  python -m tests.evaluators.run_evaluation --all
  python -m tests.evaluators.run_evaluation --component intent_router --use-llm
"""
import argparse
import asyncio
from pathlib import Path


EVALUATOR_MAP = {
    "privacy_sanitizer": ("tests.evaluators.privacy_evaluator", "PrivacyEvaluator"),
    "intent_router": ("tests.evaluators.intent_evaluator", "IntentEvaluator"),
    "insight_distiller": ("tests.evaluators.insight_evaluator", "InsightEvaluator"),
    "serendipity_matcher": ("tests.evaluators.serendipity_evaluator", "SerendipityEvaluator"),
}

GOLDEN_DIR = Path(__file__).parent.parent / "golden_datasets"
REPORTS_DIR = Path(__file__).parent.parent / "eval_reports"


async def run_eval(component: str, use_llm: bool = False):
    module_path, class_name = EVALUATOR_MAP[component]
    mod = __import__(module_path, fromlist=[class_name])
    evaluator_cls = getattr(mod, class_name)
    evaluator = evaluator_cls()

    golden_path = GOLDEN_DIR / f"{component}.json"
    if not golden_path.exists():
        print(f"Golden dataset not found: {golden_path}")
        return

    judge = None
    if use_llm:
        from app.core.llm import llm_manager
        from app.core.llm_provider import LLMUsageRole
        judge = llm_manager.get_client(LLMUsageRole.BALANCED)

    report = await evaluator.evaluate_all(golden_path, judge)

    REPORTS_DIR.mkdir(exist_ok=True)
    report_path = REPORTS_DIR / f"{component}_report.json"
    report.to_json(report_path)

    # サマリー出力
    print(f"\n{'='*60}")
    print(f"Component: {report.component}")
    print(f"Pass Rate: {report.pass_rate:.1%} ({report.passed_cases}/{report.total_cases})")
    print(f"Average Scores: {report.average_scores}")
    if report.failed_cases:
        print(f"Failed Cases ({len(report.failed_cases)}):")
        for f in report.failed_cases[:5]:
            print(f"  - {f['id']}: {f['scores']}")

        # Phase 3: 失敗ケースを自動蓄積
        _append_failures(component, report.failed_cases)
    print(f"{'='*60}\n")


def _append_failures(component, failures):
    """失敗ケースを failure_cases.json に蓄積"""
    import json, time
    failure_path = Path(__file__).parent.parent / "optimization" / "failure_cases.json"
    failure_path.parent.mkdir(exist_ok=True)

    existing = []
    if failure_path.exists():
        with open(failure_path) as f:
            existing = json.load(f)

    for case in failures:
        existing.append({
            "component": component,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            **case,
        })

    with open(failure_path, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--component", choices=list(EVALUATOR_MAP.keys()))
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--use-llm", action="store_true")
    args = parser.parse_args()

    if args.all:
        for comp in EVALUATOR_MAP:
            asyncio.run(run_eval(comp, args.use_llm))
    elif args.component:
        asyncio.run(run_eval(args.component, args.use_llm))
```

---

## 5. Phase 3: プロンプト自己最適化

### 5.1 失敗ケース蓄積

Phase 2 の評価で閾値を下回ったケースは自動的に `tests/optimization/failure_cases.json` に蓄積される（上記 `_append_failures` で実装済み）。

### 5.2 プロンプト改善エージェント

```python
# tests/optimization/prompt_optimizer.py
"""
失敗ケースを分析し、システムプロンプトの改善案を生成する。

Usage:
  python -m tests.optimization.prompt_optimizer --component intent_router
"""

OPTIMIZER_PROMPT = """あなたは LLM プロンプト最適化の専門家です。

以下の情報が与えられます:
1. 現在のシステムプロンプト
2. 失敗したテストケース（入力・期待出力・実際の出力・スコア）

タスク:
- 失敗パターンを分析し、根本原因を特定する
- システムプロンプトの**具体的な修正案**を提示する
- 修正は既存の正常ケースを壊さないように注意する

出力形式（JSON）:
{
  "analysis": "失敗パターンの分析",
  "root_causes": ["原因1", "原因2"],
  "suggested_changes": [
    {
      "location": "プロンプト内の修正箇所",
      "current": "現在の記述",
      "proposed": "提案する記述",
      "rationale": "修正理由"
    }
  ],
  "risk_assessment": "既存ケースへの影響リスク"
}
"""
```

### 5.3 A/B テスト実行

```python
# tests/optimization/ab_test_runner.py
"""
新旧プロンプトを Golden Dataset で対戦させ、勝率を比較する。

Usage:
  python -m tests.optimization.ab_test_runner \
    --component intent_router \
    --prompt-a current \
    --prompt-b proposed
"""
```

---

## 6. 実装手順（Claude Code で実行する際のチェックリスト）

### Phase 1 を始めるとき

1. `backend/tests/golden_datasets/` ディレクトリを作成
2. 対象コンポーネントの Golden Dataset JSON を作成（上記フォーマット準拠）
3. `backend/tests/unit/` に単体テストを作成
4. `pytest backend/tests/unit/ -v` で実行確認

### Phase 2 を始めるとき

1. `backend/tests/evaluators/` ディレクトリを作成
2. `base_evaluator.py` を実装
3. 対象コンポーネントの Evaluator を実装
4. `python -m tests.evaluators.run_evaluation --component <name>` で実行
5. `--use-llm` フラグで LLM Judge を有効化して再実行

### Phase 3 を始めるとき

1. Phase 2 の評価で失敗ケースが蓄積されていることを確認
2. `prompt_optimizer.py` で改善案を生成
3. `ab_test_runner.py` で新旧比較
4. 勝率が上回った場合のみプロンプトを更新

---

## 7. CI/CD 統合（GitHub Actions 例）

```yaml
# .github/workflows/quality-gate.yml
name: Quality Gate
on: [pull_request]
jobs:
  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run unit tests (no LLM)
        run: |
          cd backend
          pip install -r requirements.txt
          pytest tests/unit/ -v --tb=short

  llm-eval:
    runs-on: ubuntu-latest
    if: contains(github.event.pull_request.labels.*.name, 'eval')
    steps:
      - uses: actions/checkout@v4
      - name: Run LLM evaluation
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
        run: |
          cd backend
          pip install -r requirements.txt
          python -m tests.evaluators.run_evaluation --all --use-llm
      - name: Check scores
        run: |
          python -c "
          import json, sys
          for f in Path('backend/tests/eval_reports').glob('*_report.json'):
              report = json.load(open(f))
              if report['pass_rate'] < 0.7:
                  print(f'FAIL: {report[\"component\"]} pass_rate={report[\"pass_rate\"]:.1%}')
                  sys.exit(1)
          "
```

---

## 8. 重要な注意点

- **LLM モックの一貫性**: 単体テストでは必ず LLM をモックすること。実 API テストは `@pytest.mark.skipif` で分離する。
- **Golden Dataset のバージョン管理**: データセットは Git 管理し、変更時は PR レビューを通す。
- **評価の再現性**: LLM Judge の temperature は 0.2 以下に固定し、同一入力での揺れを最小化する。
- **プロンプト変更の影響範囲**: Phase 3 でプロンプトを変更する際は、必ず Golden Dataset 全体で回帰テストを実施する。
- **Privacy First**: テストデータに実際の個人情報を含めないこと。すべて架空のデータを使用する。
