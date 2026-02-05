"""
MINDYARD - Vertex AI Embedding Provider
Google Cloud Vertex AIを使用するEmbeddingプロバイダー実装
"""
from typing import List, Optional

from app.core.embedding_provider import (
    EmbeddingProvider,
    EmbeddingProviderConfig,
    EmbeddingProviderType,
)


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

    サポートモデル:
    - text-embedding-004 (768次元, 推奨)
    - text-embedding-005 (768次元, 最新)
    - text-multilingual-embedding-002 (768次元, 多言語対応)
    - textembedding-gecko@003 (768次元)
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
        self._model = None

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
            import vertexai
            from vertexai.language_models import TextEmbeddingModel

            # Vertex AIの初期化
            if self._project_id:
                vertexai.init(project=self._project_id, location=self._location)
            else:
                vertexai.init(location=self._location)

            # モデルの初期化
            self._model = TextEmbeddingModel.from_pretrained(self.config.model)
            self._initialized = True

        except ImportError:
            raise ImportError(
                "google-cloud-aiplatform package is required for Vertex AI provider. "
                "Install it with: pip install google-cloud-aiplatform"
            )
        except Exception as e:
            raise RuntimeError(f"Failed to initialize Vertex AI Embedding: {e}")

    @property
    def model(self):
        """初期化済みモデルを取得"""
        if self._model is None:
            raise RuntimeError("Provider not initialized. Call initialize() first.")
        return self._model

    async def embed_text(self, text: str) -> Optional[List[float]]:
        """単一テキストの埋め込みベクトルを取得"""
        await self.initialize()

        try:
            # Vertex AIのembedding APIは同期的なので、実行
            embeddings = self.model.get_embeddings([text])
            if embeddings and len(embeddings) > 0:
                return embeddings[0].values
            return None

        except Exception as e:
            return None

    async def embed_texts(self, texts: List[str]) -> Optional[List[List[float]]]:
        """複数テキストの埋め込みベクトルを一括取得"""
        await self.initialize()

        try:
            # Vertex AIは一度に最大250テキストまで処理可能
            # バッチサイズを超える場合は分割
            batch_size = 250
            all_embeddings = []

            for i in range(0, len(texts), batch_size):
                batch = texts[i:i + batch_size]
                embeddings = self.model.get_embeddings(batch)
                all_embeddings.extend([e.values for e in embeddings])

            return all_embeddings

        except Exception as e:
            return None
