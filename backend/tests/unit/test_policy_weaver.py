"""
PolicyWeaver 単体テスト

2層テスト:
  Layer A: LLM なし — extract_json_from_text のパース処理を検証
  Layer B: LLM モック — MockLLMProvider で PolicyWeaver.extract_policies を検証

PolicyWeaver は llm_manager.get_client() を内部で呼ぶため、
テストでは llm_manager.get_client をパッチして MockLLMProvider を返す。
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from app.core.llm import extract_json_from_text
from app.schemas.policy import BoundaryConditions, ExtractedPolicy, ExtractionResult
from app.services.layer3.policy_weaver import PolicyWeaver
from tests.conftest import MockLLMProvider, POLICY_PRESETS

GOLDEN_DATA = Path(__file__).parent.parent / "golden_datasets" / "policy_weaver.json"


@pytest.fixture
def golden_cases():
    with open(GOLDEN_DATA, encoding="utf-8") as f:
        data = json.load(f)
    return data["cases"]


@pytest.fixture
def weaver():
    return PolicyWeaver()


# ================================================================
# Layer A: LLM なしのパース・バリデーションテスト
# ================================================================

class TestPolicyWeaverParsing:
    """LLM を使わずに JSON パースとスキーマバリデーションを検証"""

    def test_extract_json_valid_policy(self):
        raw = json.dumps({
            "policies": [{
                "dilemma_context": "パフォーマンスと開発速度のトレードオフ",
                "principle": "初期はDjangoを選択する",
                "boundary_conditions": {
                    "applies_when": ["チーム5人以下"],
                    "except_when": ["同時接続1万超え"],
                },
            }]
        })
        parsed = extract_json_from_text(raw)
        assert parsed is not None
        assert "policies" in parsed
        assert len(parsed["policies"]) == 1

    def test_extract_json_empty_policies(self):
        raw = json.dumps({"policies": []})
        parsed = extract_json_from_text(raw)
        assert parsed is not None
        assert parsed["policies"] == []

    def test_extract_json_from_markdown_block(self):
        raw = '```json\n{"policies": [{"dilemma_context": "test", "principle": "rule", "boundary_conditions": {"applies_when": [], "except_when": []}}]}\n```'
        parsed = extract_json_from_text(raw)
        assert parsed is not None
        assert len(parsed["policies"]) == 1

    def test_extracted_policy_model(self):
        policy = ExtractedPolicy(
            dilemma_context="テスト背景",
            principle="テストルール",
            boundary_conditions=BoundaryConditions(
                applies_when=["条件A"],
                except_when=["例外B"],
            ),
        )
        assert policy.dilemma_context == "テスト背景"
        assert policy.principle == "テストルール"
        assert len(policy.boundary_conditions.applies_when) == 1
        assert len(policy.boundary_conditions.except_when) == 1

    def test_extracted_policy_default_boundary(self):
        policy = ExtractedPolicy(
            dilemma_context="背景",
            principle="ルール",
        )
        assert policy.boundary_conditions.applies_when == []
        assert policy.boundary_conditions.except_when == []

    def test_extraction_result_model(self):
        result = ExtractionResult(policies=[
            ExtractedPolicy(
                dilemma_context="d1",
                principle="p1",
            ),
        ])
        assert len(result.policies) == 1
        assert result.raw_log_summary is None

    def test_compute_ttl_expiry(self, weaver):
        from datetime import datetime, timezone
        expiry = PolicyWeaver.compute_ttl_expiry(days=30)
        assert expiry.tzinfo is not None
        delta = expiry - datetime.now(timezone.utc)
        assert 29 <= delta.days <= 30

    def test_compute_ttl_expiry_custom_days(self, weaver):
        from datetime import datetime, timezone
        expiry = PolicyWeaver.compute_ttl_expiry(days=90)
        delta = expiry - datetime.now(timezone.utc)
        assert 89 <= delta.days <= 90


# ================================================================
# Layer B: LLM モックを使ったコンポーネントテスト
# ================================================================

class TestPolicyWeaverWithLLM:
    """MockLLMProvider を使って PolicyWeaver の全体フローを検証"""

    @pytest.mark.asyncio
    async def test_extract_policies_tech_tradeoff(self, weaver):
        """技術選定のジレンマからポリシーが抽出される"""
        mock_provider = MockLLMProvider(preset_json=POLICY_PRESETS["tech_tradeoff"])
        with patch(
            "app.services.layer3.policy_weaver.llm_manager"
        ) as mock_manager:
            mock_manager.get_client.return_value = mock_provider

            result = await weaver.extract_policies(
                logs=["パフォーマンスと開発速度のトレードオフでDjangoを選んだ"],
                project_context="社内SaaS開発",
            )

        assert len(result.policies) == 1
        policy = result.policies[0]
        assert "Django" in policy.principle
        assert len(policy.boundary_conditions.applies_when) >= 1
        assert len(policy.boundary_conditions.except_when) >= 1
        assert mock_provider.call_count == 1

    @pytest.mark.asyncio
    async def test_extract_policies_security_proxy(self, weaver):
        """セキュリティポリシーが正しくパースされる"""
        mock_provider = MockLLMProvider(preset_json=POLICY_PRESETS["security_proxy"])
        with patch(
            "app.services.layer3.policy_weaver.llm_manager"
        ) as mock_manager:
            mock_manager.get_client.return_value = mock_provider

            result = await weaver.extract_policies(
                logs=["セキュリティ要件で外部APIへの直接通信を禁止した"],
                project_context="金融系API開発",
            )

        assert len(result.policies) == 1
        policy = result.policies[0]
        assert "プロキシ" in policy.principle
        assert len(policy.boundary_conditions.applies_when) >= 1

    @pytest.mark.asyncio
    async def test_extract_policies_no_policy(self, weaver):
        """雑談ログからはポリシーが抽出されない"""
        mock_provider = MockLLMProvider(preset_json=POLICY_PRESETS["no_policy"])
        with patch(
            "app.services.layer3.policy_weaver.llm_manager"
        ) as mock_manager:
            mock_manager.get_client.return_value = mock_provider

            result = await weaver.extract_policies(
                logs=["おはよう", "今日の天気いいね"],
            )

        assert len(result.policies) == 0

    @pytest.mark.asyncio
    async def test_extract_policies_empty_logs(self, weaver):
        """空のログリストでは LLM を呼ばず空結果を返す"""
        result = await weaver.extract_policies(logs=[])
        assert len(result.policies) == 0

    @pytest.mark.asyncio
    async def test_extract_policies_malformed_response(self, weaver):
        """不正な JSON レスポンスでもクラッシュしない"""
        mock_provider = MockLLMProvider(preset_json={})
        with patch(
            "app.services.layer3.policy_weaver.llm_manager"
        ) as mock_manager:
            mock_manager.get_client.return_value = mock_provider

            result = await weaver.extract_policies(
                logs=["テスト入力"],
            )

        assert len(result.policies) == 0

    @pytest.mark.asyncio
    async def test_extract_policies_partial_items(self, weaver):
        """一部のポリシーが不完全でもスキップして残りを返す"""
        preset = {
            "policies": [
                {
                    "dilemma_context": "正常なポリシー",
                    "principle": "正常なルール",
                    "boundary_conditions": {
                        "applies_when": ["条件A"],
                        "except_when": [],
                    },
                },
                {
                    "invalid_field": "不正なポリシー",
                },
            ]
        }
        mock_provider = MockLLMProvider(preset_json=preset)
        with patch(
            "app.services.layer3.policy_weaver.llm_manager"
        ) as mock_manager:
            mock_manager.get_client.return_value = mock_provider

            result = await weaver.extract_policies(
                logs=["テスト入力"],
            )

        assert len(result.policies) == 1
        assert result.policies[0].principle == "正常なルール"

    @pytest.mark.asyncio
    async def test_build_user_message_with_context(self, weaver):
        """プロジェクトコンテキスト付きのメッセージ構築"""
        msg = weaver._build_user_message("ログ内容", "プロジェクトA")
        assert "プロジェクト情報" in msg
        assert "プロジェクトA" in msg
        assert "ログ内容" in msg

    @pytest.mark.asyncio
    async def test_build_user_message_without_context(self, weaver):
        """プロジェクトコンテキストなしのメッセージ構築"""
        msg = weaver._build_user_message("ログ内容", None)
        assert "プロジェクト情報" not in msg
        assert "ログ内容" in msg

    @pytest.mark.asyncio
    async def test_messages_contain_system_prompt(self, weaver):
        """LLM に送られるメッセージにシステムプロンプトが含まれる"""
        mock_provider = MockLLMProvider(preset_json=POLICY_PRESETS["tech_tradeoff"])
        with patch(
            "app.services.layer3.policy_weaver.llm_manager"
        ) as mock_manager:
            mock_manager.get_client.return_value = mock_provider

            await weaver.extract_policies(
                logs=["テスト"],
                project_context="テストプロジェクト",
            )

        messages = mock_provider.last_messages
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert "Policy Weaver" in messages[0]["content"]
        assert messages[1]["role"] == "user"

    @pytest.mark.asyncio
    async def test_enforcement_level_defaults_to_suggest(self):
        """DB モデルのデフォルト enforcement_level が suggest であることを確認"""
        from app.models.policy import EnforcementLevel
        assert EnforcementLevel.SUGGEST.value == "suggest"


# ================================================================
# Golden Dataset ベースのパラメトライズドテスト
# ================================================================

class TestPolicyWeaverGoldenEasy:
    """Golden Dataset の easy ケースで基本動作を検証"""

    @pytest.fixture
    def easy_cases(self, golden_cases):
        return [c for c in golden_cases if c.get("difficulty") == "easy"]

    @pytest.mark.asyncio
    async def test_golden_easy_has_policies(self, weaver, easy_cases):
        """easy ケースのうちポリシー期待ありのケースで正しくプリセット応答が処理される"""
        for case in easy_cases:
            expected_has = case["expected"]["has_policies"]
            if expected_has:
                mock_provider = MockLLMProvider(
                    preset_json=POLICY_PRESETS["tech_tradeoff"]
                )
            else:
                mock_provider = MockLLMProvider(
                    preset_json=POLICY_PRESETS["no_policy"]
                )

            with patch(
                "app.services.layer3.policy_weaver.llm_manager"
            ) as mock_manager:
                mock_manager.get_client.return_value = mock_provider

                result = await weaver.extract_policies(
                    logs=case["input"]["logs"],
                    project_context=case["input"].get("project_context"),
                )

            if expected_has:
                assert len(result.policies) >= 1, (
                    f"Case {case['id']}: expected policies but got 0"
                )
            else:
                assert len(result.policies) == 0, (
                    f"Case {case['id']}: expected no policies but got {len(result.policies)}"
                )
