"""
PLURA バックエンド - 共通テストフィクスチャ

設計方針:
- LLMプロバイダーをモック化し、外部API（OpenAI/Vertex）を一切呼び出さない
- テスト用プリセットレスポンスで各コンポーネントの挙動を検証する
- 各テストは独立して実行可能（サービス起動不要）
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Type, TypeVar

import pytest
from pydantic import BaseModel

from app.core.llm_provider import (
    LLMProvider,
    LLMProviderConfig,
    LLMResponse,
    LLMUsageRole,
    ProviderType,
)

T = TypeVar("T", bound=BaseModel)


# =============================================================================
# MockLLMProvider
# テスト用の LLMProvider 実装。外部 API を一切呼び出さず、
# プリセットされた JSON レスポンスを返す。
# =============================================================================

class MockLLMProvider(LLMProvider):
    """
    外部 API を呼び出さないテスト専用 LLMProvider。

    - `preset_json`: generate_json() が返すプリセットデータ
    - `call_count`: 呼び出し回数（テスト内で検証可能）
    - `last_messages`: 最後に受け取ったメッセージリスト
    """

    def __init__(self, preset_json: Optional[Dict[str, Any]] = None):
        config = LLMProviderConfig(
            provider=ProviderType.OPENAI,
            model="mock-gpt-test",
        )
        super().__init__(config)
        self._preset_json: Dict[str, Any] = preset_json or {}
        self.call_count: int = 0
        self.last_messages: List[Dict[str, str]] = []

    @property
    def provider_type(self) -> ProviderType:
        return ProviderType.OPENAI

    async def initialize(self) -> None:
        """初期化は no-op"""
        self._initialized = True

    async def generate_text(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        self.call_count += 1
        self.last_messages = messages
        return LLMResponse(
            content=json.dumps(self._preset_json),
            model="mock-gpt-test",
            provider=ProviderType.OPENAI,
        )

    async def generate_structured_output(
        self,
        messages: List[Dict[str, str]],
        response_model: Type[T],
        temperature: Optional[float] = None,
    ) -> T:
        self.call_count += 1
        self.last_messages = messages
        return response_model(**self._preset_json)

    async def generate_json(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
    ) -> Dict[str, Any]:
        self.call_count += 1
        self.last_messages = messages
        return self._preset_json


# =============================================================================
# プリセットレスポンス集
# 各コンポーネントが LLM から受け取ることを期待する JSON 構造を定義する
# =============================================================================

# --- Layer 1: IntentRouter ---
INTENT_PRESETS: Dict[str, Dict[str, Any]] = {
    "knowledge": {
        "previous_evaluation": "none",
        "primary_intent": "knowledge",
        "primary_confidence": 0.91,
        "secondary_intent": "deep_dive",
        "secondary_confidence": 0.28,
        "needs_probing": False,
        "reasoning": "User is asking a factual question.",
    },
    "empathy": {
        "previous_evaluation": "none",
        "primary_intent": "empathy",
        "primary_confidence": 0.87,
        "secondary_intent": "chat",
        "secondary_confidence": 0.18,
        "needs_probing": False,
        "reasoning": "User is venting negative emotions.",
    },
    "brainstorm": {
        "previous_evaluation": "positive",
        "primary_intent": "brainstorm",
        "primary_confidence": 0.88,
        "secondary_intent": "deep_dive",
        "secondary_confidence": 0.25,
        "needs_probing": False,
        "reasoning": "User wants to generate ideas.",
    },
    "state_share": {
        "previous_evaluation": "none",
        "primary_intent": "state_share",
        "primary_confidence": 0.93,
        "secondary_intent": "chat",
        "secondary_confidence": 0.12,
        "needs_probing": False,
        "reasoning": "User is sharing their current state.",
    },
    "deep_dive": {
        "previous_evaluation": "pivot",
        "primary_intent": "deep_dive",
        "primary_confidence": 0.85,
        "secondary_intent": "knowledge",
        "secondary_confidence": 0.30,
        "needs_probing": False,
        "reasoning": "User wants to deeply analyze a problem.",
    },
    "probe": {
        "previous_evaluation": "none",
        "primary_intent": "knowledge",
        "primary_confidence": 0.52,
        "secondary_intent": "deep_dive",
        "secondary_confidence": 0.48,
        "needs_probing": True,
        "reasoning": "Ambiguous input, clarification needed.",
    },
}

# --- Layer 2: PrivacySanitizer ---
SANITIZER_PRESETS: Dict[str, Dict[str, Any]] = {
    "with_pii": {
        "sanitized_text": "今日、[担当者]と[クライアント企業]のプロジェクトについて話した。",
        "replacements": [
            {"type": "name", "original": "田中さん", "replacement": "[担当者]"},
            {"type": "name", "original": "Acme社", "replacement": "[クライアント企業]"},
        ],
    },
    "no_pii": {
        "sanitized_text": "今日は良い天気でした。",
        "replacements": [],
    },
}

# --- Layer 3: SerendipityMatcher ---
SYNERGY_PRESETS: Dict[str, Dict[str, Any]] = {
    "team_found": {
        "team_found": True,
        "project_name": "リモートワーク改善プロジェクト",
        "reason": "異なる専門領域を持つメンバーが補完的なチームを構成できます。",
        "members": [
            {
                "insight_id": "insight-001",
                "display_name": "フロントエンド開発者",
                "role": "ハッカー",
            },
            {
                "insight_id": "insight-002",
                "display_name": "UXデザイナー",
                "role": "ヒップスター",
            },
        ],
    },
    "no_team": {
        "team_found": False,
    },
}

# --- Layer 3: PolicyWeaver ---
POLICY_PRESETS: Dict[str, Dict[str, Any]] = {
    "tech_tradeoff": {
        "policies": [
            {
                "dilemma_context": "パフォーマンスと開発速度のトレードオフで、初期フェーズではモノリシックフレームワークを選択するか、マイクロサービスで始めるかの判断が必要だった。",
                "principle": "初期フェーズはDjangoを選択し、スケール要件が明確になった時点でマイクロサービス化を検討する",
                "boundary_conditions": {
                    "applies_when": [
                        "初期フェーズのプロダクト開発時",
                        "チーム規模が5人以下の場合",
                    ],
                    "except_when": [
                        "同時接続数が1万を超えることが確定している場合",
                    ],
                },
            }
        ]
    },
    "security_proxy": {
        "policies": [
            {
                "dilemma_context": "セキュリティ要件と開発効率のバランス。本番環境のセキュリティを確保しつつ、開発環境では効率的に作業できる構成が求められた。",
                "principle": "外部APIへの通信はプロキシサーバー経由を原則とし、開発環境のみプロキシ省略を許可する",
                "boundary_conditions": {
                    "applies_when": [
                        "本番環境での外部API通信時",
                        "ステージング環境でのテスト実行時",
                    ],
                    "except_when": [
                        "ローカル開発環境での動作確認時",
                    ],
                },
            }
        ]
    },
    "no_policy": {
        "policies": []
    },
}


# =============================================================================
# フィクスチャ: MockLLMProvider ファクトリー
# =============================================================================

@pytest.fixture
def make_mock_provider():
    """
    プリセットキーを指定して MockLLMProvider を生成するファクトリー。

    使用例:
        router._provider = make_mock_provider("knowledge", "intent")
        sanitizer._provider = make_mock_provider("with_pii", "sanitizer")
    """
    preset_map = {
        "intent": INTENT_PRESETS,
        "sanitizer": SANITIZER_PRESETS,
        "synergy": SYNERGY_PRESETS,
        "policy": POLICY_PRESETS,
    }

    def _factory(preset_key: str, preset_type: str = "intent") -> MockLLMProvider:
        presets = preset_map.get(preset_type, {})
        preset = presets.get(preset_key, {})
        return MockLLMProvider(preset_json=preset)

    return _factory


# =============================================================================
# フィクスチャ: コンポーネント別（LLM モック済みインスタンス）
# =============================================================================

@pytest.fixture
def intent_router_with_llm(make_mock_provider):
    """LLM が knowledge にプリセットされた IntentRouter インスタンス"""
    from app.services.layer1.intent_router import IntentRouter
    router = IntentRouter()
    router._provider = make_mock_provider("knowledge", "intent")
    return router


@pytest.fixture
def privacy_sanitizer_with_llm(make_mock_provider):
    """LLM が with_pii にプリセットされた PrivacySanitizer インスタンス"""
    from app.services.layer2.privacy_sanitizer import PrivacySanitizer
    sanitizer = PrivacySanitizer()
    sanitizer._provider = make_mock_provider("with_pii", "sanitizer")
    return sanitizer


@pytest.fixture
def serendipity_matcher_with_llm(make_mock_provider):
    """LLM が team_found にプリセットされた SerendipityMatcher インスタンス"""
    from app.services.layer3.serendipity_matcher import SerendipityMatcher
    matcher = SerendipityMatcher()
    matcher._llm_provider = make_mock_provider("team_found", "synergy")
    return matcher


@pytest.fixture
def policy_weaver_with_llm(make_mock_provider):
    """LLM が tech_tradeoff にプリセットされた PolicyWeaver インスタンス"""
    from app.services.layer3.policy_weaver import PolicyWeaver
    weaver = PolicyWeaver()
    weaver._provider = make_mock_provider("tech_tradeoff", "policy")
    return weaver
