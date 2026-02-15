"""
PLURA - LLM Manager
マルチプロバイダー対応のLLMマネージャー（シングルトン）

用途（LLMUsageRole）に応じて適切なプロバイダーとモデルの組み合わせを返却する。
"""
import json
import re
from enum import Enum
from typing import Any, Dict, List, Optional, Type, TypeVar

from pydantic import BaseModel

from app.core.config import settings
from app.core.llm_provider import (
    LLMProvider,
    LLMProviderConfig,
    LLMResponse,
    LLMUsageRole,
    ProviderType,
)


T = TypeVar("T", bound=BaseModel)


# 後方互換性のためModelTierをLLMUsageRoleのエイリアスとして提供
class ModelTier(str, Enum):
    """モデルの選択パターン（後方互換性のために残す）"""
    DEEP = "deep"
    BALANCED = "balanced"
    FAST = "fast"


# Reasoningモデルのパターン（後方互換性のために残す）
REASONING_MODEL_PATTERNS = [
    r"^o1",
    r"^gpt-5",
    r"reasoning",
]


def get_model_name(tier: ModelTier) -> str:
    """指定されたティアのモデル名を取得（後方互換性のために残す）"""
    model_map = {
        ModelTier.DEEP: settings.llm_model_deep,
        ModelTier.BALANCED: settings.llm_model_balanced,
        ModelTier.FAST: settings.llm_model_fast,
    }
    return model_map.get(tier, settings.llm_model_balanced)


def is_reasoning_model(model_name: str) -> bool:
    """モデルがreasoningモデルかどうかを判定（後方互換性のために残す）"""
    for pattern in REASONING_MODEL_PATTERNS:
        if re.search(pattern, model_name, re.IGNORECASE):
            return True
    return False


def extract_json_from_text(text: str) -> Optional[Dict[str, Any]]:
    """テキストからJSONを抽出（後方互換性のために残す）"""
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass

    json_patterns = [
        r"```json\s*([\s\S]*?)\s*```",
        r"```\s*([\s\S]*?)\s*```",
        r"\{[\s\S]*\}",
    ]

    for pattern in json_patterns:
        matches = re.findall(pattern, text)
        for match in matches:
            try:
                if isinstance(match, str):
                    json_str = match if pattern == r"\{[\s\S]*\}" else match
                    return json.loads(json_str.strip())
            except json.JSONDecodeError:
                continue

    return None


class LLMManager:
    """
    LLMマネージャー（シングルトン）

    用途（LLMUsageRole）に応じて適切なプロバイダーとモデルの組み合わせを返却する。
    プロバイダーインスタンスはキャッシュされ、再利用される。
    """

    _instance: Optional["LLMManager"] = None
    _providers: Dict[str, LLMProvider] = {}

    def __new__(cls) -> "LLMManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._providers = {}
        return cls._instance

    def _create_provider(self, config: Dict[str, Any]) -> LLMProvider:
        """設定からプロバイダーインスタンスを作成"""
        provider_type = config.get("provider", "openai").lower()
        model = config.get("model", "gpt-4o")
        temperature = config.get("temperature", 0.3)
        max_tokens = config.get("max_tokens")

        provider_config = LLMProviderConfig(
            provider=ProviderType(provider_type),
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        if provider_type == "openai":
            from app.core.providers.openai import OpenAIProvider
            return OpenAIProvider(
                config=provider_config,
                api_key=settings.openai_api_key,
            )
        elif provider_type == "vertex":
            from app.core.providers.google_genai import GoogleGenAIClient
            return GoogleGenAIClient(
                config=provider_config,
                project_id=settings.google_cloud_project,
                location="us-central1",
            )
        else:
            raise ValueError(f"Unknown provider type: {provider_type}")

    def _get_cache_key(self, role: LLMUsageRole) -> str:
        """キャッシュキーを生成"""
        config = settings.get_llm_config(role.value)
        return f"{config.get('provider', 'openai')}:{config.get('model', 'default')}"

    def get_client(self, role: LLMUsageRole) -> LLMProvider:
        """
        用途に応じたLLMプロバイダーを取得

        Args:
            role: LLMUsageRole (FAST, BALANCED, DEEP)

        Returns:
            設定に基づいた適切なLLMProviderインスタンス
        """
        cache_key = self._get_cache_key(role)

        if cache_key not in self._providers:
            config = settings.get_llm_config(role.value)
            provider = self._create_provider(config)
            self._providers[cache_key] = provider

        return self._providers[cache_key]

    def get_provider_for_role(self, role: LLMUsageRole) -> LLMProvider:
        """get_clientのエイリアス（より明示的な名前）"""
        return self.get_client(role)

    async def is_available(self, role: LLMUsageRole) -> bool:
        """
        指定された用途のプロバイダーが利用可能かどうかを確認

        Args:
            role: LLMUsageRole

        Returns:
            True: プロバイダーが利用可能
            False: プロバイダーが利用不可
        """
        try:
            provider = self.get_client(role)
            return await provider.health_check()
        except Exception:
            return False

    def get_config_for_role(self, role: LLMUsageRole) -> Dict[str, Any]:
        """用途に応じた設定を取得"""
        return settings.get_llm_config(role.value)

    def clear_cache(self) -> None:
        """プロバイダーキャッシュをクリア"""
        self._providers.clear()


# シングルトンインスタンス
llm_manager = LLMManager()


# 後方互換性のためのLLMClientクラス
class LLMClient:
    """
    LLMクライアント（後方互換性のために残す）

    新しいコードではLLMManagerを使用することを推奨。
    """

    def __init__(self, tier: ModelTier = ModelTier.BALANCED):
        self.tier = tier
        self._role = LLMUsageRole(tier.value)
        self._provider: Optional[LLMProvider] = None

    @property
    def model(self) -> str:
        """現在のモデル名を取得"""
        config = settings.get_llm_config(self._role.value)
        return config.get("model", settings.llm_model_balanced)

    @property
    def is_reasoning(self) -> bool:
        """reasoningモデルかどうか"""
        return is_reasoning_model(self.model)

    def _get_provider(self) -> LLMProvider:
        """プロバイダーを取得（遅延初期化）"""
        if self._provider is None:
            self._provider = llm_manager.get_client(self._role)
        return self._provider

    @property
    def client(self):
        """
        OpenAIクライアントの遅延初期化（後方互換性）

        注意: プロバイダーがOpenAIでない場合はエラーとなる
        """
        provider = self._get_provider()
        if hasattr(provider, "client"):
            return provider.client
        raise AttributeError(
            "Current provider does not expose a direct client. "
            "Use LLMManager.get_client() instead."
        )

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        json_response: bool = True,
    ) -> Dict[str, Any]:
        """
        チャット補完を実行（後方互換性）

        Args:
            messages: メッセージのリスト
            temperature: 温度パラメータ
            json_response: JSONレスポンスを期待するかどうか

        Returns:
            パースされたレスポンス（json_response=Trueの場合）またはテキスト
        """
        provider = self._get_provider()
        await provider.initialize()

        if json_response:
            return await provider.generate_json(messages, temperature)
        else:
            response = await provider.generate_text(messages, temperature)
            return {"content": response.content}

    def get_model_info(self) -> Dict[str, Any]:
        """モデル情報を取得"""
        provider = self._get_provider()
        return provider.get_model_info()


def create_llm_client(tier: ModelTier) -> LLMClient:
    """
    指定されたティアのLLMクライアントを作成（後方互換性のために残す）

    新しいコードではllm_manager.get_client(LLMUsageRole.XXX)を使用することを推奨。
    """
    return LLMClient(tier=tier)
