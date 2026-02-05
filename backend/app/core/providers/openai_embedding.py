"""
MINDYARD - OpenAI Embedding Provider
OpenAI APIを使用するEmbeddingプロバイダー実装
"""
from typing import List, Optional

from openai import AsyncOpenAI

from app.core.embedding_provider import (
    EmbeddingProvider,
    EmbeddingProviderConfig,
    EmbeddingProviderType,
)


# OpenAI Embeddingモデルの次元数マッピング
OPENAI_EMBEDDING_DIMENSIONS = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
}


class OpenAIEmbeddingProvider(EmbeddingProvider):
    """
    OpenAI APIを使用するEmbeddingプロバイダー

    サポートモデル:
    - text-embedding-3-small (1536次元, 推奨)
    - text-embedding-3-large (3072次元, 高精度)
    - text-embedding-ada-002 (1536次元, レガシー)
    """

    def __init__(self, config: EmbeddingProviderConfig, api_key: Optional[str] = None):
        super().__init__(config)
        self._api_key = api_key
        self._client: Optional[AsyncOpenAI] = None

    @property
    def provider_type(self) -> EmbeddingProviderType:
        return EmbeddingProviderType.OPENAI

    @property
    def vector_size(self) -> int:
        """埋め込みベクトルの次元数"""
        # configで明示的に指定されている場合はそれを使用
        if self.config.dimensions:
            return self.config.dimensions
        # モデル名から次元数を取得
        return OPENAI_EMBEDDING_DIMENSIONS.get(self.config.model, 1536)

    async def initialize(self) -> None:
        """OpenAIクライアントを初期化"""
        if self._initialized:
            return

        if not self._api_key:
            raise ValueError("OpenAI API key is not configured")

        self._client = AsyncOpenAI(api_key=self._api_key)
        self._initialized = True

    @property
    def client(self) -> AsyncOpenAI:
        """初期化済みクライアントを取得"""
        if self._client is None:
            raise RuntimeError("Provider not initialized. Call initialize() first.")
        return self._client

    async def embed_text(self, text: str) -> Optional[List[float]]:
        """単一テキストの埋め込みベクトルを取得"""
        await self.initialize()

        try:
            kwargs = {
                "model": self.config.model,
                "input": text,
            }

            # text-embedding-3-* モデルは次元数指定をサポート
            if self.config.dimensions and self.config.model.startswith("text-embedding-3"):
                kwargs["dimensions"] = self.config.dimensions

            response = await self.client.embeddings.create(**kwargs)
            return response.data[0].embedding

        except Exception as e:
            return None

    async def embed_texts(self, texts: List[str]) -> Optional[List[List[float]]]:
        """複数テキストの埋め込みベクトルを一括取得"""
        await self.initialize()

        try:
            kwargs = {
                "model": self.config.model,
                "input": texts,
            }

            if self.config.dimensions and self.config.model.startswith("text-embedding-3"):
                kwargs["dimensions"] = self.config.dimensions

            response = await self.client.embeddings.create(**kwargs)
            return [data.embedding for data in response.data]

        except Exception as e:
            return None
