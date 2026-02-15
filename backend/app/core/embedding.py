"""
PLURA - Embedding Manager
マルチプロバイダー対応のEmbeddingマネージャー（シングルトン）
"""
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.core.embedding_provider import (
    EmbeddingProvider,
    EmbeddingProviderConfig,
    EmbeddingProviderType,
)


class EmbeddingManager:
    """
    Embeddingマネージャー（シングルトン）

    設定に基づいて適切なEmbeddingプロバイダーを返却する。
    プロバイダーインスタンスはキャッシュされ、再利用される。
    """

    _instance: Optional["EmbeddingManager"] = None
    _provider: Optional[EmbeddingProvider] = None

    def __new__(cls) -> "EmbeddingManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._provider = None
        return cls._instance

    def _create_provider(self, config: Dict[str, Any]) -> EmbeddingProvider:
        """設定からプロバイダーインスタンスを作成"""
        provider_type = config.get("provider", "openai").lower()
        model = config.get("model", "text-embedding-3-small")
        dimensions = config.get("dimensions")

        provider_config = EmbeddingProviderConfig(
            provider=EmbeddingProviderType(provider_type),
            model=model,
            dimensions=dimensions,
        )

        if provider_type == "openai":
            from app.core.providers.openai_embedding import OpenAIEmbeddingProvider
            return OpenAIEmbeddingProvider(
                config=provider_config,
                api_key=settings.openai_api_key,
            )
        elif provider_type == "vertex":
            from app.core.providers.vertex_embedding import VertexAIEmbeddingProvider
            return VertexAIEmbeddingProvider(
                config=provider_config,
                project_id=settings.google_cloud_project,
                location="us-central1",
            )
        else:
            raise ValueError(f"Unknown embedding provider type: {provider_type}")

    def get_provider(self) -> EmbeddingProvider:
        """
        Embeddingプロバイダーを取得

        Returns:
            設定に基づいた適切なEmbeddingProviderインスタンス
        """
        if self._provider is None:
            config = settings.get_embedding_config()
            self._provider = self._create_provider(config)

        return self._provider

    async def is_available(self) -> bool:
        """
        Embeddingプロバイダーが利用可能かどうかを確認

        Returns:
            True: プロバイダーが利用可能
            False: プロバイダーが利用不可
        """
        try:
            provider = self.get_provider()
            return await provider.health_check()
        except Exception:
            return False

    def get_config(self) -> Dict[str, Any]:
        """現在のEmbedding設定を取得"""
        return settings.get_embedding_config()

    def get_vector_size(self) -> int:
        """現在のプロバイダーのベクトル次元数を取得"""
        provider = self.get_provider()
        return provider.vector_size

    def clear_cache(self) -> None:
        """プロバイダーキャッシュをクリア"""
        self._provider = None


# シングルトンインスタンス
embedding_manager = EmbeddingManager()
