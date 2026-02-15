"""
MINDYARD - Knowledge Graph Store
Layer 3: 承認されたInsight Cardを格納するベクトルデータベース

マルチプロバイダー対応のEmbeddingを使用。
"""
import uuid
from typing import Dict, List, Optional

from qdrant_client import QdrantClient
from qdrant_client.http import models

from app.core.config import settings
from app.core.embedding import embedding_manager
from app.core.embedding_provider import EmbeddingProvider


class KnowledgeStore:
    """
    Knowledge Graph Store (ナレッジ・グラフ)

    機能:
    - インサイトのベクトル化と保存
    - 意味的類似検索
    - 関連インサイトの取得

    マルチプロバイダー対応のEmbeddingを使用（OpenAI / Vertex AI）。
    """

    def __init__(self):
        self._embedding_provider: Optional[EmbeddingProvider] = None
        self.qdrant_client: Optional[QdrantClient] = None
        self.collection_name = settings.qdrant_collection_name
        self._initialized = False

    def _get_embedding_provider(self) -> Optional[EmbeddingProvider]:
        """Embeddingプロバイダーを取得（遅延初期化）"""
        if self._embedding_provider is None:
            try:
                self._embedding_provider = embedding_manager.get_provider()
            except Exception as e:
                logger.error(f"Failed to get embedding provider: {e}", exc_info=True)
        return self._embedding_provider

    async def initialize(self):
        """Qdrantコレクションの初期化"""
        if self._initialized:
            return

        try:
            self.qdrant_client = QdrantClient(
                host=settings.qdrant_host,
                port=settings.qdrant_port,
            )

            # Embeddingプロバイダーからベクトルサイズを取得
            embedding_provider = self._get_embedding_provider()
            vector_size = embedding_provider.vector_size if embedding_provider else 1536

            # コレクションが存在しない場合は作成
            collections = self.qdrant_client.get_collections().collections
            collection_names = [c.name for c in collections]

            if self.collection_name not in collection_names:
                self.qdrant_client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=models.VectorParams(
                        size=vector_size,
                        distance=models.Distance.COSINE,
                    ),
                )

            self._initialized = True

        except Exception as e:
            logger.error(f"Failed to Qdrant connection: {e}", exc_info=True)
            # Qdrantに接続できない場合はNoneのまま
            self.qdrant_client = None

    async def _get_embedding(self, text: str) -> Optional[List[float]]:
        """テキストの埋め込みベクトルを取得"""
        embedding_provider = self._get_embedding_provider()
        if not embedding_provider:
            return None

        try:
            await embedding_provider.initialize()
            return await embedding_provider.embed_text(text)
        except Exception as e:
            logger.error(f"Failed to generate embedding: {e}", exc_info=True)
            return None

    async def store_insight(self, insight_id: str, insight: Dict) -> Optional[str]:
        """
        インサイトをベクトルDBに保存

        Args:
            insight_id: インサイトのUUID
            insight: インサイトの内容

        Returns:
            vector_id: 保存されたベクトルのID
        """
        if not self.qdrant_client:
            await self.initialize()

        embedding_provider = self._get_embedding_provider()
        if not self.qdrant_client or not embedding_provider:
            return None

        # 検索用テキストの構築
        search_text = self._build_search_text(insight)

        # 埋め込みベクトルの取得
        embedding = await self._get_embedding(search_text)
        if not embedding:
            return None

        vector_id = str(uuid.uuid4())

        try:
            self.qdrant_client.upsert(
                collection_name=self.collection_name,
                points=[
                    models.PointStruct(
                        id=vector_id,
                        vector=embedding,
                        payload={
                            "insight_id": insight_id,
                            "title": insight.get("title", ""),
                            "summary": insight.get("summary", ""),
                            "topics": insight.get("topics", []),
                            "tags": insight.get("tags", []),
                        },
                    )
                ],
            )
            return vector_id

        except Exception as e:
            logger.error(f"Failed to qdrant upsert: {e}", exc_info=True)
            return None

    async def search_similar(
        self,
        query: str,
        limit: int = 5,
        score_threshold: float = 0.7,
        filter_tags: Optional[List[str]] = None,
    ) -> List[Dict]:
        """
        類似インサイトを検索

        Args:
            query: 検索クエリ
            limit: 取得件数
            score_threshold: 類似度の閾値
            filter_tags: 検索対象を絞り込むタグ（OR条件）

        Returns:
            類似インサイトのリスト
        """
        if not self.qdrant_client:
            await self.initialize()

        embedding_provider = self._get_embedding_provider()
        if not self.qdrant_client or not embedding_provider:
            return []

        # クエリの埋め込み
        query_embedding = await self._get_embedding(query)
        if not query_embedding:
            return []

        try:
            query_filter = None
            normalized_tags = self._normalize_filter_tags(filter_tags)
            if normalized_tags:
                query_filter = models.Filter(
                    must=[
                        models.FieldCondition(
                            key="tags",
                            match=models.MatchAny(any=normalized_tags),
                        )
                    ]
                )

            results = self.qdrant_client.search(
                collection_name=self.collection_name,
                query_vector=query_embedding,
                limit=limit,
                score_threshold=score_threshold,
                query_filter=query_filter,
            )

            return [
                {
                    "insight_id": hit.payload.get("insight_id"),
                    "title": hit.payload.get("title"),
                    "summary": hit.payload.get("summary"),
                    "topics": hit.payload.get("topics", []),
                    "tags": hit.payload.get("tags", []),
                    "score": hit.score,
                }
                for hit in results
            ]

        except Exception as e:
            return []

    def _normalize_filter_tags(self, tags: Optional[List[str]]) -> List[str]:
        if not tags:
            return []

        normalized: List[str] = []
        for tag in tags:
            if not isinstance(tag, str):
                continue
            value = tag.strip()
            if value and value not in normalized:
                normalized.append(value)
        return normalized

    def _build_search_text(self, insight: Dict) -> str:
        """検索用テキストを構築"""
        parts = [
            insight.get("title", ""),
            insight.get("context", ""),
            insight.get("problem", ""),
            insight.get("solution", ""),
            insight.get("summary", ""),
        ]

        topics = insight.get("topics", [])
        if topics:
            parts.append(" ".join(topics))

        tags = insight.get("tags", [])
        if tags:
            parts.append(" ".join(tags))

        return " ".join(filter(None, parts))

    async def delete_insight(self, vector_id: str) -> bool:
        """インサイトをベクトルDBから削除"""
        if not self.qdrant_client:
            await self.initialize()

        if not self.qdrant_client:
            return False

        try:
            self.qdrant_client.delete(
                collection_name=self.collection_name,
                points_selector=models.PointIdsList(
                    points=[vector_id],
                ),
            )
            return True
        except Exception as e:
            return False


# シングルトンインスタンス
knowledge_store = KnowledgeStore()
