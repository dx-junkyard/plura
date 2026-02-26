"""
Phase 2 Evaluator フレームワークのテスト

BaseEvaluator、各コンポーネント Evaluator のルールベース評価を検証する。
LLM を使わず、MockLLMProvider を活用して動作確認する。
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Tuple
from unittest.mock import AsyncMock, patch

import pytest

from tests.evaluators.base_evaluator import BaseEvaluator, EvalCase, EvalReport


# ================================================================
# テスト用の具象 Evaluator
# ================================================================

class DummyEvaluator(BaseEvaluator):
    """テスト用のダミー Evaluator"""

    def __init__(self):
        super().__init__("DummyComponent", pass_threshold=6.0)
        self._mock_output: Dict = {}

    @property
    def scoring_dimensions(self) -> List[Dict[str, str]]:
        return [
            {"name": "accuracy", "description": "正確性"},
            {"name": "quality", "description": "品質"},
        ]

    async def run_component(self, input_data: Dict) -> Dict:
        return self._mock_output

    def build_judge_prompt(
        self, input_data: Dict, output: Dict, expected: Dict
    ) -> str:
        return f"Evaluate: input={input_data}, output={output}, expected={expected}"

    def _rule_based_check(
        self, input_data: Dict, output: Dict, expected: Dict
    ) -> Tuple[Dict[str, float], str]:
        # 入力テキストに "good" が含まれていれば高スコア
        text = input_data.get("text", "")
        if "good" in text:
            return {"accuracy": 9.0, "quality": 8.0}, "Good input"
        return {"accuracy": 3.0, "quality": 3.0}, "Bad input"


# ================================================================
# BaseEvaluator テスト
# ================================================================

class TestEvalCase:
    """EvalCase データクラスのテスト"""

    def test_default_values(self):
        case = EvalCase(
            case_id="TC-001",
            input_data={"text": "test"},
            actual_output={"result": "ok"},
            expected={"intent": "chat"},
        )
        assert case.case_id == "TC-001"
        assert case.scores == {}
        assert case.reasoning == ""
        assert case.passed is True

    def test_with_scores(self):
        case = EvalCase(
            case_id="TC-002",
            input_data={},
            actual_output={},
            expected={},
            scores={"accuracy": 8.0},
            reasoning="Good",
            passed=True,
        )
        assert case.scores["accuracy"] == 8.0


class TestEvalReport:
    """EvalReport データクラスのテスト"""

    def test_pass_rate(self):
        report = EvalReport(
            component="Test",
            timestamp="2025-01-01T00:00:00",
            total_cases=10,
            passed_cases=7,
            average_scores={"accuracy": 7.5},
            min_scores={"accuracy": 3.0},
            failed_cases=[],
            details=[],
        )
        assert report.pass_rate == 0.7

    def test_pass_rate_zero_cases(self):
        report = EvalReport(
            component="Test",
            timestamp="2025-01-01T00:00:00",
            total_cases=0,
            passed_cases=0,
            average_scores={},
            min_scores={},
            failed_cases=[],
            details=[],
        )
        assert report.pass_rate == 0

    def test_to_json(self, tmp_path):
        report = EvalReport(
            component="Test",
            timestamp="2025-01-01T00:00:00",
            total_cases=5,
            passed_cases=4,
            average_scores={"accuracy": 8.0},
            min_scores={"accuracy": 5.0},
            failed_cases=[{"id": "T-001", "scores": {"accuracy": 3.0}, "reasoning": "Bad"}],
            details=[],
        )
        path = tmp_path / "test_report.json"
        report.to_json(path)
        assert path.exists()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["component"] == "Test"
        assert data["total_cases"] == 5

    def test_to_markdown(self):
        report = EvalReport(
            component="TestComp",
            timestamp="2025-01-01T00:00:00",
            total_cases=10,
            passed_cases=8,
            average_scores={"accuracy": 8.5, "quality": 7.2},
            min_scores={"accuracy": 5.0, "quality": 3.0},
            failed_cases=[{"id": "T-001", "scores": {"accuracy": 3.0}, "reasoning": "Bad"}],
            details=[],
        )
        md = report.to_markdown()
        assert "TestComp" in md
        assert "80.0%" in md
        assert "accuracy" in md
        assert "T-001" in md


class TestBaseEvaluator:
    """BaseEvaluator のテスト"""

    @pytest.fixture
    def evaluator(self):
        return DummyEvaluator()

    async def test_evaluate_single_rule_based_pass(self, evaluator):
        evaluator._mock_output = {"result": "good_output"}
        case = {
            "id": "TC-001",
            "input": {"text": "this is good input"},
            "expected": {"intent": "chat"},
        }
        result = await evaluator.evaluate_single(case)
        assert result.case_id == "TC-001"
        assert result.scores["accuracy"] == 9.0
        assert result.scores["quality"] == 8.0
        assert result.passed is True

    async def test_evaluate_single_rule_based_fail(self, evaluator):
        evaluator._mock_output = {"result": "bad_output"}
        case = {
            "id": "TC-002",
            "input": {"text": "this is bad input"},
            "expected": {"intent": "chat"},
        }
        result = await evaluator.evaluate_single(case)
        assert result.scores["accuracy"] == 3.0
        assert result.passed is False

    async def test_evaluate_single_component_error(self, evaluator):
        """コンポーネント実行がエラーを投げた場合"""
        async def failing_run(input_data):
            raise RuntimeError("Component crashed")

        evaluator.run_component = failing_run
        case = {
            "id": "TC-003",
            "input": {"text": "crash test"},
            "expected": {},
        }
        result = await evaluator.evaluate_single(case)
        assert result.passed is False
        assert "Component execution failed" in result.reasoning

    async def test_evaluate_all_with_golden_dataset(self, evaluator, tmp_path):
        evaluator._mock_output = {"result": "ok"}
        dataset = {
            "component": "Test",
            "version": "1.0",
            "cases": [
                {"id": "TC-001", "input": {"text": "good case"}, "expected": {}},
                {"id": "TC-002", "input": {"text": "bad case"}, "expected": {}},
                {"id": "TC-003", "input": {"text": "another good case"}, "expected": {}},
            ],
        }
        golden_path = tmp_path / "test.json"
        golden_path.write_text(json.dumps(dataset), encoding="utf-8")

        report = await evaluator.evaluate_all(golden_path)
        assert report.total_cases == 3
        assert report.component == "DummyComponent"
        assert "accuracy" in report.average_scores

    async def test_evaluate_single_with_llm_judge(self, evaluator):
        """LLM Judge を使った評価"""
        evaluator._mock_output = {"result": "output"}

        mock_provider = AsyncMock()
        mock_provider.initialize = AsyncMock()
        mock_provider.generate_json = AsyncMock(return_value={
            "scores": {"accuracy": 8, "quality": 7},
            "reasoning": "Good output quality",
        })

        case = {
            "id": "TC-004",
            "input": {"text": "test input"},
            "expected": {"intent": "chat"},
        }
        result = await evaluator.evaluate_single(case, judge_provider=mock_provider)
        assert result.scores["accuracy"] == 8
        assert result.scores["quality"] == 7
        assert result.passed is True
        assert "Good output quality" in result.reasoning

    async def test_evaluate_single_with_llm_judge_missing_dims(self, evaluator):
        """LLM Judge が一部の軸を返さなかった場合"""
        evaluator._mock_output = {"result": "output"}

        mock_provider = AsyncMock()
        mock_provider.initialize = AsyncMock()
        mock_provider.generate_json = AsyncMock(return_value={
            "scores": {"accuracy": 9},  # quality が欠落
            "reasoning": "Partial scores",
        })

        case = {
            "id": "TC-005",
            "input": {"text": "test"},
            "expected": {},
        }
        result = await evaluator.evaluate_single(case, judge_provider=mock_provider)
        # 欠落した軸は 1.0 (最低点) が補完されるべき
        assert result.scores["quality"] == 1.0
        assert result.passed is False  # quality=1.0 < threshold=6.0


# ================================================================
# IntentEvaluator テスト
# ================================================================

class TestIntentEvaluator:
    """IntentEvaluator のルールベース評価テスト"""

    @pytest.fixture
    def evaluator(self):
        from tests.evaluators.intent_evaluator import IntentEvaluator
        return IntentEvaluator()

    def test_scoring_dimensions(self, evaluator):
        dims = evaluator.scoring_dimensions
        assert len(dims) == 3
        names = [d["name"] for d in dims]
        assert "intent_accuracy" in names
        assert "confidence_calibration" in names
        assert "probe_appropriateness" in names

    def test_rule_based_correct_intent(self, evaluator):
        input_data = {"text": "眠い"}
        output = {
            "primary_intent": "state_share",
            "primary_confidence": 0.8,
            "needs_probing": False,
        }
        expected = {
            "primary_intent": "state_share",
            "min_confidence": 0.5,
        }
        scores, reason = evaluator._rule_based_check(input_data, output, expected)
        assert scores["intent_accuracy"] == 10.0
        assert scores["confidence_calibration"] >= 8.0

    def test_rule_based_wrong_intent(self, evaluator):
        input_data = {"text": "test"}
        output = {
            "primary_intent": "chat",
            "primary_confidence": 0.6,
            "needs_probing": False,
        }
        expected = {
            "primary_intent": "deep_dive",
            "min_confidence": 0.5,
        }
        scores, reason = evaluator._rule_based_check(input_data, output, expected)
        assert scores["intent_accuracy"] < 6.0

    def test_rule_based_prohibited_intent(self, evaluator):
        input_data = {"text": "test"}
        output = {
            "primary_intent": "chat",
            "primary_confidence": 0.6,
            "needs_probing": False,
        }
        expected = {
            "primary_intent": "deep_dive",
            "min_confidence": 0.5,
            "should_not_be": ["chat"],
        }
        scores, reason = evaluator._rule_based_check(input_data, output, expected)
        assert scores["intent_accuracy"] == 1.0

    async def test_run_component(self, evaluator, make_mock_provider):
        """MockLLMProvider を使ったコンポーネント実行"""
        router = evaluator._get_router()
        router._provider = make_mock_provider("knowledge", "intent")
        result = await evaluator.run_component({"text": "Pythonの使い方を教えて"})
        assert "intent" in result
        assert "primary_intent" in result
        assert "confidence" in result

    def test_build_judge_prompt(self, evaluator):
        prompt = evaluator.build_judge_prompt(
            input_data={"text": "テスト入力"},
            output={
                "primary_intent": "chat",
                "secondary_intent": "knowledge",
                "primary_confidence": 0.8,
                "secondary_confidence": 0.2,
                "needs_probing": False,
                "reasoning": "test",
            },
            expected={"primary_intent": "chat", "min_confidence": 0.5},
        )
        assert "テスト入力" in prompt
        assert "chat" in prompt


# ================================================================
# PrivacyEvaluator テスト
# ================================================================

class TestPrivacyEvaluator:
    """PrivacyEvaluator のルールベース評価テスト"""

    @pytest.fixture
    def evaluator(self):
        from tests.evaluators.privacy_evaluator import PrivacyEvaluator
        return PrivacyEvaluator()

    def test_scoring_dimensions(self, evaluator):
        dims = evaluator.scoring_dimensions
        assert len(dims) == 3
        names = [d["name"] for d in dims]
        assert "pii_removal" in names
        assert "context_preservation" in names
        assert "naturalness" in names

    def test_rule_based_pii_removed(self, evaluator):
        input_data = {"text": "田中さんに連絡ください。メール: tanaka@example.com"}
        output = {
            "sanitized_text": "[担当者]に連絡ください。メール: [メールアドレス]",
        }
        expected = {
            "pii_removed": True,
            "should_not_contain": ["tanaka@example.com", "田中"],
            "should_contain": ["[メールアドレス]"],
        }
        scores, reason = evaluator._rule_based_check(input_data, output, expected)
        assert scores["pii_removal"] == 10.0
        assert scores["context_preservation"] >= 5.0

    def test_rule_based_pii_remaining(self, evaluator):
        input_data = {"text": "田中さんの電話: 090-1234-5678"}
        output = {
            "sanitized_text": "田中さんの電話: 090-1234-5678",
        }
        expected = {
            "pii_removed": True,
            "should_not_contain": ["090-1234-5678", "田中"],
        }
        scores, reason = evaluator._rule_based_check(input_data, output, expected)
        assert scores["pii_removal"] == 1.0  # 即時フェイル

    def test_rule_based_false_positive(self, evaluator):
        input_data = {"text": "今日は良い天気でした。"}
        output = {
            "sanitized_text": "今日は良い天気でした。",
        }
        expected = {
            "pii_removed": False,
        }
        scores, reason = evaluator._rule_based_check(input_data, output, expected)
        assert scores["pii_removal"] == 10.0
        assert scores["context_preservation"] == 10.0

    async def test_run_component(self, evaluator, make_mock_provider):
        """MockLLMProvider を使ったコンポーネント実行"""
        sanitizer = evaluator._get_sanitizer()
        sanitizer._provider = make_mock_provider("with_pii", "sanitizer")
        result = await evaluator.run_component(
            {"text": "田中さんにメール: tanaka@example.com"}
        )
        assert "sanitized_text" in result
        assert "metadata" in result


# ================================================================
# InsightEvaluator テスト
# ================================================================

class TestInsightEvaluator:
    """InsightEvaluator のルールベース評価テスト"""

    @pytest.fixture
    def evaluator(self):
        from tests.evaluators.insight_evaluator import InsightEvaluator
        return InsightEvaluator()

    def test_scoring_dimensions(self, evaluator):
        dims = evaluator.scoring_dimensions
        assert len(dims) == 3
        names = [d["name"] for d in dims]
        assert "structure_quality" in names
        assert "suitability_judgment" in names
        assert "abstraction_quality" in names

    def test_rule_based_suitable_well_structured(self, evaluator):
        input_data = {"text": "スクラムのスプリントプランニングで改善した"}
        output = {
            "title": "スプリントプランニング改善の知見",
            "context": "アジャイル開発プロジェクトで",
            "problem": "ベロシティの見積もり精度が低い",
            "solution": "過去3スプリントの平均を使用",
            "summary": "ベロシティ改善のベストプラクティス",
            "topics": ["アジャイル", "スプリントプランニング"],
            "tags": ["ベストプラクティス", "改善"],
            "not_suitable": False,
        }
        expected = {
            "is_suitable": True,
            "expected_title_keywords": ["スプリント"],
            "expected_topics": ["アジャイル"],
        }
        scores, reason = evaluator._rule_based_check(input_data, output, expected)
        assert scores["suitability_judgment"] == 10.0
        assert scores["structure_quality"] >= 7.0
        assert scores["abstraction_quality"] >= 6.0

    def test_rule_based_not_suitable_correct(self, evaluator):
        input_data = {"text": "おはよう"}
        output = {
            "title": "",
            "context": "",
            "problem": "",
            "solution": "",
            "summary": "",
            "topics": [],
            "tags": [],
            "not_suitable": True,
        }
        expected = {
            "is_suitable": False,
            "rejection_reason": "雑談",
        }
        scores, reason = evaluator._rule_based_check(input_data, output, expected)
        assert scores["suitability_judgment"] == 10.0
        assert scores["structure_quality"] == 10.0

    def test_rule_based_false_negative(self, evaluator):
        """適格な入力が not_suitable と判定された場合"""
        input_data = {"text": "重要な技術的知見"}
        output = {
            "not_suitable": True,
            "title": "",
        }
        expected = {
            "is_suitable": True,
        }
        scores, reason = evaluator._rule_based_check(input_data, output, expected)
        assert scores["suitability_judgment"] == 2.0


# ================================================================
# SerendipityEvaluator テスト
# ================================================================

class TestSerendipityEvaluator:
    """SerendipityEvaluator のルールベース評価テスト"""

    @pytest.fixture
    def evaluator(self):
        from tests.evaluators.serendipity_evaluator import SerendipityEvaluator
        return SerendipityEvaluator()

    def test_scoring_dimensions(self, evaluator):
        dims = evaluator.scoring_dimensions
        assert len(dims) == 3
        names = [d["name"] for d in dims]
        assert "team_formation" in names
        assert "role_complementarity" in names
        assert "synergy_quality" in names

    def test_rule_based_team_found(self, evaluator):
        input_data = {"text": "test"}
        output = {
            "team_found": True,
            "recommendations": [{
                "project_name": "テストプロジェクト",
                "reason": "補完的なチーム",
                "team_members": [
                    {"display_name": "A", "role": "ハッカー"},
                    {"display_name": "B", "role": "ヒップスター"},
                    {"display_name": "C", "role": "ハスラー"},
                ],
            }],
        }
        expected = {
            "team_found": True,
            "expected_roles": ["ハッカー", "ヒップスター", "ハスラー"],
        }
        scores, reason = evaluator._rule_based_check(input_data, output, expected)
        assert scores["team_formation"] == 10.0
        assert scores["role_complementarity"] == 10.0
        assert scores["synergy_quality"] >= 8.0

    def test_rule_based_team_not_found_expected(self, evaluator):
        input_data = {"text": "test"}
        output = {
            "team_found": False,
            "recommendations": [],
        }
        expected = {
            "team_found": False,
        }
        scores, reason = evaluator._rule_based_check(input_data, output, expected)
        assert scores["team_formation"] == 10.0

    def test_rule_based_team_found_unexpected(self, evaluator):
        """チーム不成立が期待されるのにチームが成立した場合"""
        input_data = {"text": "test"}
        output = {
            "team_found": True,
            "recommendations": [{
                "project_name": "不要なプロジェクト",
                "reason": "類似メンバー",
                "team_members": [
                    {"display_name": "A", "role": "ハッカー"},
                    {"display_name": "B", "role": "ハッカー"},
                ],
            }],
        }
        expected = {
            "team_found": False,
        }
        scores, reason = evaluator._rule_based_check(input_data, output, expected)
        assert scores["team_formation"] == 2.0


# ================================================================
# PolicyEvaluator テスト
# ================================================================

class TestPolicyEvaluator:
    """PolicyEvaluator のルールベース評価テスト"""

    @pytest.fixture
    def evaluator(self):
        from tests.evaluators.policy_evaluator import PolicyEvaluator
        return PolicyEvaluator()

    def test_scoring_dimensions(self, evaluator):
        dims = evaluator.scoring_dimensions
        assert len(dims) == 3
        names = [d["name"] for d in dims]
        assert "heuristic_compliance" in names
        assert "boundary_clarity" in names
        assert "ttl_appropriateness" in names

    def test_rule_based_policies_extracted_correctly(self, evaluator):
        """ポリシーが正しく抽出された場合、高スコア"""
        input_data = {
            "logs": ["パフォーマンスと開発速度のトレードオフで悩んだ"],
            "project_context": "社内SaaS",
        }
        output = {
            "policy_count": 1,
            "policies": [{
                "dilemma_context": "パフォーマンスと開発速度のトレードオフで、初期フェーズではモノリシックフレームワークを選択するか判断が必要だった。",
                "principle": "初期フェーズはDjangoを選択し、スケール要件が明確になった時点でマイクロサービス化を検討する",
                "boundary_conditions": {
                    "applies_when": ["初期フェーズのプロダクト開発時", "チーム規模が5人以下の場合"],
                    "except_when": ["同時接続数が1万を超えることが確定している場合"],
                },
            }],
        }
        expected = {
            "has_policies": True,
            "min_policies": 1,
            "max_policies": 3,
            "expected_principle_keywords": ["Django"],
            "enforcement_level": "suggest",
            "boundary_conditions_defined": True,
            "expected_applies_when_count": 1,
            "expected_except_when_count": 1,
        }
        scores, reason = evaluator._rule_based_check(input_data, output, expected)
        assert scores["heuristic_compliance"] >= 8.0
        assert scores["boundary_clarity"] >= 7.0
        assert scores["ttl_appropriateness"] >= 7.0

    def test_rule_based_no_policy_expected_and_empty(self, evaluator):
        """ポリシー不要で正しく空の場合、全軸10点"""
        input_data = {"logs": ["おはよう"], "project_context": None}
        output = {"policy_count": 0, "policies": []}
        expected = {
            "has_policies": False,
            "min_policies": 0,
            "max_policies": 0,
            "expected_principle_keywords": [],
            "enforcement_level": "suggest",
            "boundary_conditions_defined": False,
            "expected_applies_when_count": 0,
            "expected_except_when_count": 0,
        }
        scores, reason = evaluator._rule_based_check(input_data, output, expected)
        assert scores["heuristic_compliance"] == 10.0
        assert scores["boundary_clarity"] == 10.0
        assert scores["ttl_appropriateness"] == 10.0

    def test_rule_based_expected_policy_but_empty(self, evaluator):
        """ポリシーがあるべきなのに空の場合、全軸低スコア"""
        input_data = {"logs": ["技術選定のトレードオフ"], "project_context": None}
        output = {"policy_count": 0, "policies": []}
        expected = {
            "has_policies": True,
            "min_policies": 1,
            "max_policies": 3,
        }
        scores, reason = evaluator._rule_based_check(input_data, output, expected)
        assert scores["heuristic_compliance"] <= 3.0
        assert scores["boundary_clarity"] <= 3.0
        assert scores["ttl_appropriateness"] <= 3.0

    def test_rule_based_unexpected_policy_extracted(self, evaluator):
        """ポリシー不要なのに抽出された場合、低スコア"""
        input_data = {"logs": ["おはよう"], "project_context": None}
        output = {
            "policy_count": 1,
            "policies": [{
                "dilemma_context": "不要なポリシー",
                "principle": "不要なルール",
                "boundary_conditions": {
                    "applies_when": [],
                    "except_when": [],
                },
            }],
        }
        expected = {
            "has_policies": False,
            "min_policies": 0,
            "max_policies": 0,
        }
        scores, reason = evaluator._rule_based_check(input_data, output, expected)
        assert scores["heuristic_compliance"] <= 4.0
        assert "不要" in reason

    def test_rule_based_block_language_detected(self, evaluator):
        """BLOCK的な記述がある場合、heuristic_compliance が下がる"""
        input_data = {"logs": ["ルール策定"], "project_context": None}
        output = {
            "policy_count": 1,
            "policies": [{
                "dilemma_context": "セキュリティ上の理由から外部通信を禁止する必要がある",
                "principle": "外部APIへの直接通信は絶対にしないこと",
                "boundary_conditions": {
                    "applies_when": ["本番環境"],
                    "except_when": [],
                },
            }],
        }
        expected = {
            "has_policies": True,
            "min_policies": 1,
            "max_policies": 3,
            "expected_except_when_count": 0,
        }
        scores, reason = evaluator._rule_based_check(input_data, output, expected)
        assert scores["heuristic_compliance"] <= 5.0

    def test_rule_based_empty_boundary_conditions(self, evaluator):
        """applies_when が空の場合、boundary_clarity が低い"""
        input_data = {"logs": ["テスト"], "project_context": None}
        output = {
            "policy_count": 1,
            "policies": [{
                "dilemma_context": "短い",
                "principle": "ルール",
                "boundary_conditions": {
                    "applies_when": [],
                    "except_when": [],
                },
            }],
        }
        expected = {
            "has_policies": True,
            "min_policies": 1,
            "max_policies": 3,
            "expected_applies_when_count": 1,
            "expected_except_when_count": 0,
        }
        scores, reason = evaluator._rule_based_check(input_data, output, expected)
        assert scores["boundary_clarity"] < 6.0

    def test_rule_based_perpetual_language_detected(self, evaluator):
        """永続的ルールの示唆がある場合、ttl_appropriateness が下がる"""
        input_data = {"logs": ["テスト"], "project_context": None}
        output = {
            "policy_count": 1,
            "policies": [{
                "dilemma_context": "永久に変更不可のルールとして定めた",
                "principle": "恒久的にこのルールを適用する",
                "boundary_conditions": {
                    "applies_when": ["全プロジェクト"],
                    "except_when": [],
                },
            }],
        }
        expected = {
            "has_policies": True,
            "min_policies": 1,
            "max_policies": 3,
            "expected_except_when_count": 0,
        }
        scores, reason = evaluator._rule_based_check(input_data, output, expected)
        assert scores["ttl_appropriateness"] <= 4.0

    def test_rule_based_review_mention_bonus(self, evaluator):
        """再評価の言及がある場合、ttl_appropriateness にボーナス"""
        input_data = {"logs": ["テスト"], "project_context": None}
        output = {
            "policy_count": 1,
            "policies": [{
                "dilemma_context": "3ヶ月後に見直しを行う前提で決定した",
                "principle": "初期フェーズでは簡易方式を採用する",
                "boundary_conditions": {
                    "applies_when": ["初期フェーズ"],
                    "except_when": [],
                },
            }],
        }
        expected = {
            "has_policies": True,
            "min_policies": 1,
            "max_policies": 3,
            "expected_except_when_count": 0,
        }
        scores, reason = evaluator._rule_based_check(input_data, output, expected)
        assert scores["ttl_appropriateness"] >= 8.0

    def test_build_judge_prompt(self, evaluator):
        prompt = evaluator.build_judge_prompt(
            input_data={
                "logs": ["テストログ"],
                "project_context": "テストプロジェクト",
            },
            output={
                "policies": [{
                    "dilemma_context": "テストジレンマ",
                    "principle": "テストルール",
                    "boundary_conditions": {
                        "applies_when": ["条件A"],
                        "except_when": ["例外B"],
                    },
                }],
                "policy_count": 1,
            },
            expected={
                "has_policies": True,
                "expected_principle_keywords": ["テスト"],
            },
        )
        assert "テストログ" in prompt
        assert "テストプロジェクト" in prompt
        assert "テストジレンマ" in prompt
        assert "テストルール" in prompt
        assert "条件A" in prompt
        assert "例外B" in prompt

    def test_build_judge_prompt_empty_policies(self, evaluator):
        prompt = evaluator.build_judge_prompt(
            input_data={"logs": ["雑談"], "project_context": None},
            output={"policies": [], "policy_count": 0},
            expected={"has_policies": False},
        )
        assert "ポリシーなし" in prompt

    async def test_run_component(self, evaluator, make_mock_provider):
        """MockLLMProvider を使ったコンポーネント実行"""
        weaver = evaluator._get_weaver()
        mock_provider = make_mock_provider("tech_tradeoff", "policy")
        with patch(
            "app.services.layer3.policy_weaver.llm_manager"
        ) as mock_manager:
            mock_manager.get_client.return_value = mock_provider

            result = await evaluator.run_component({
                "logs": ["技術選定ログ"],
                "project_context": "テスト",
            })

        assert "policies" in result
        assert "policy_count" in result
        assert result["policy_count"] == 1
