"""
PLURA - Vertex AI Embedding Provider
Google Cloud Vertex AIを使用するEmbeddingプロバイダー実装
"""
import asyncio
import logging
from typing import List, Optional

from google import genai
from google.genai import types

from app.core.embedding_provider import (
    EmbeddingProvider,
    EmbeddingProviderConfig,
    EmbeddingProviderType,
)

logger = logging.getLogger(__name__)

# Vertex AI Embeddingモデルの次元数マッピング
VERTEX_EMBEDDING_DIMENSIONS = {
    "text-embedding-004": 768,
    "text-embedding-005": 768,
    "text-multilingual-embedding-002": 768,
    "textembedding-gecko@003": 768,
    "textembedding-gecko@002": 768,
    "textembedding-gecko@001": 768,
    "textembedding-gecko-multilingual@001": 768,
}


class VertexAIEmbeddingProvider(EmbeddingProvider):
    """
    Google Cloud Vertex AIを使用するEmbeddingプロバイダー
    """

    def __init__(
        self,
        config: EmbeddingProviderConfig,
        project_id: Optional[str] = None,
        location: str = "us-central1",
    ):
        super().__init__(config)
        self._project_id = project_id
        self._location = location
        self._client: Optional[genai.Client] = None

    @property
    def provider_type(self) -> EmbeddingProviderType:
        return EmbeddingProviderType.VERTEX

    @property
    def vector_size(self) -> int:
        """埋め込みベクトルの次元数"""
        if self.config.dimensions:
            return self.config.dimensions
        return VERTEX_EMBEDDING_DIMENSIONS.get(self.config.model, 768)

    async def initialize(self) -> None:
        """Vertex AIクライアントを初期化"""
        if self._initialized:
            return

        try:
            # Vertex AIの初期化
            self._client = genai.Client(
                vertexai=True,
                project=self._project_id,
                location=self._location
            )
            self._initialized = True

        except Exception as e:
            logger.error(f"Failed to initialize Vertex AI Client: {e}", exc_info=True)
            raise RuntimeError(f"Failed to initialize Vertex AI Embedding: {e}")

    @property
    def client(self) -> genai.Client:
        """初期化済みクライアントを取得"""
        if self._client is None:
            raise RuntimeError("Provider not initialized. Call initialize() first.")
        return self._client

    async def embed_text(self, text: str) -> Optional[List[float]]:
        """単一テキストの埋め込みベクトルを取得"""
        await self.initialize()

        try:
            # 同期メソッド(embed_content)を非同期コンテキストで実行
            loop = asyncio.get_running_loop()
            response = await self.client.aio.models.embed_content(
                model=self.config.model,
                contents=text,
            )

            if response.embeddings and len(response.embeddings) > 0:
                return response.embeddings[0].values
            
            logger.warning(f"Vertex AI returned no embeddings for text: {text[:50]}...")
            return None

        except Exception as e:
            logger.error(f"Vertex AI embed_text failed: {e}", exc_info=True)
            return None

    async def embed_texts(self, texts: List[str]) -> Optional[List[List[float]]]:
        """複数テキストの埋め込みベクトルを一括取得"""
        await self.initialize()

        try:
            # Vertex AIは一度に最大250テキストまで処理可能
            batch_size = 250
            all_embeddings = []
            loop = asyncio.get_running_loop()

            for i in range(0, len(texts), batch_size):
                batch = texts[i:i + batch_size]

                # 同期メソッドを非同期コンテキストで実行
                response = await self.client.aio.models.embed_content(
                    model=self.config.model,
                    contents=batch,
                )

                if response.embeddings:
                    all_embeddings.extend([e.values for e in response.embeddings])

            return all_embeddings

        except Exception as e:
            logger.error(f"Vertex AI embed_texts failed: {e}", exc_info=True)
            return None
