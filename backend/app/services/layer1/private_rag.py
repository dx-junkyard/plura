"""
PLURA - Private RAG Service
Layer 1: ユーザー専用のベクトルDB検索（Private Space）

ユーザーがアップロードしたPDFから抽出したテキストチャンクを
ユーザーIDでフィルタリングしたQdrantコレクションに格納し、
会話中にプライベートドキュメントから関連情報を検索する。
"""
import logging
import uuid
from typing import Dict, List, Optional

from qdrant_client import QdrantClient
from qdrant_client.http import models

from app.core.config import settings
from app.core.embedding import embedding_manager
from app.core.embedding_provider import EmbeddingProvider

logger = logging.getLogger(__name__)

# チャンク分割の設定
CHUNK_SIZE = 800       # 文字数
CHUNK_OVERLAP = 100    # オーバーラップ文字数


def split_text_into_chunks(
    text: str,
    chunk_size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
) -> List[str]:
    """テキストを固定長チャンクに分割（オーバーラップ付き）"""
    if not text or len(text) <= chunk_size:
        return [text] if text else []

    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        if chunk.strip():
            chunks.append(chunk.strip())
        start += chunk_size - overlap

    return chunks


class PrivateRAG:
    """
    Private RAG Service

    ユーザー専用ドキュメントのベクトル検索を提供する。
    共有 Qdrant コレクション内で user_id によるフィルタリングで
    プライバシーを確保する。
    """

    def __init__(self):
        self._embedding_provider: Optional[EmbeddingProvider] = None
        self.qdrant_client: Optional[QdrantClient] = None
        self.collection_name = settings.qdrant_private_collection_name
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

            embedding_provider = self._get_embedding_provider()
            vector_size = embedding_provider.vector_size if embedding_provider else 1536

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
                logger.info(f"Created Qdrant collection: {self.collection_name}")

            self._initialized = True
        except Exception as e:
            logger.error(f"Failed to initialize Qdrant: {e}", exc_info=True)
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

    async def store_chunks(
        self,
        document_id: str,
        user_id: str,
        filename: str,
        chunks: List[str],
    ) -> int:
        """
        テキストチャンクをQdrantに格納

        Returns:
            格納に成功したチャンク数
        """
        if not self.qdrant_client:
            await self.initialize()

        embedding_provider = self._get_embedding_provider()
        if not self.qdrant_client or not embedding_provider:
            return 0

        stored_count = 0
        for i, chunk in enumerate(chunks):
            embedding = await self._get_embedding(chunk)
            if not embedding:
                continue

            point_id = str(uuid.uuid4())
            try:
                self.qdrant_client.upsert(
                    collection_name=self.collection_name,
                    points=[
                        models.PointStruct(
                            id=point_id,
                            vector=embedding,
                            payload={
                                "document_id": document_id,
                                "user_id": user_id,
                                "filename": filename,
                                "chunk_index": i,
                                "text": chunk,
                            },
                        )
                    ],
                )
                stored_count += 1
            except Exception as e:
                logger.error(
                    f"Failed to store chunk {i} for document {document_id}: {e}",
                    exc_info=True,
                )

        logger.info(
            f"Stored {stored_count}/{len(chunks)} chunks for document {document_id}"
        )
        return stored_count

    async def search(
        self,
        query: str,
        user_id: str,
        limit: int = 5,
        score_threshold: float = 0.5,
    ) -> List[Dict]:
        """
        ユーザーのプライベートドキュメントから関連チャンクを検索

        Args:
            query: 検索クエリ
            user_id: ユーザーID（プライバシーフィルタ）
            limit: 取得件数
            score_threshold: 類似度の閾値

        Returns:
            関連チャンクのリスト
        """
        if not self.qdrant_client:
            await self.initialize()

        embedding_provider = self._get_embedding_provider()
        if not self.qdrant_client or not embedding_provider:
            return []

        query_embedding = await self._get_embedding(query)
        if not query_embedding:
            return []

        try:
            results = self.qdrant_client.search(
                collection_name=self.collection_name,
                query_vector=query_embedding,
                limit=limit,
                score_threshold=score_threshold,
                query_filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="user_id",
                            match=models.MatchValue(value=user_id),
                        )
                    ]
                ),
            )

            return [
                {
                    "document_id": hit.payload.get("document_id"),
                    "filename": hit.payload.get("filename"),
                    "chunk_index": hit.payload.get("chunk_index"),
                    "text": hit.payload.get("text"),
                    "score": hit.score,
                }
                for hit in results
            ]
        except Exception as e:
            logger.error(f"Failed to search private docs: {e}", exc_info=True)
            return []

    async def delete_document_chunks(self, document_id: str) -> bool:
        """ドキュメントのすべてのチャンクを削除"""
        if not self.qdrant_client:
            await self.initialize()

        if not self.qdrant_client:
            return False

        try:
            self.qdrant_client.delete(
                collection_name=self.collection_name,
                points_selector=models.FilterSelector(
                    filter=models.Filter(
                        must=[
                            models.FieldCondition(
                                key="document_id",
                                match=models.MatchValue(value=document_id),
                            )
                        ]
                    )
                ),
            )
            logger.info(f"Deleted all chunks for document {document_id}")
            return True
        except Exception as e:
            logger.error(
                f"Failed to delete chunks for document {document_id}: {e}",
                exc_info=True,
            )
            return False


# シングルトンインスタンス
private_rag = PrivateRAG()
