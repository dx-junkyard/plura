"""
MINDYARD - Embedding Provider Abstract Interface
マルチプロバイダー対応のEmbedding抽象インターフェース
"""
from abc import ABC, abstractmethod
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel


class EmbeddingProviderType(str, Enum):
    """サポートするEmbeddingプロバイダータイプ"""
    OPENAI = "openai"
    VERTEX = "vertex"


class EmbeddingProviderConfig(BaseModel):
    """Embeddingプロバイダー設定"""
    provider: EmbeddingProviderType
    model: str
    dimensions: Optional[int] = None  # 一部のモデルでは次元数を指定可能


class EmbeddingProvider(ABC):
    """
    Embeddingプロバイダーの抽象基底クラス

    全てのプロバイダー実装はこのクラスを継承し、
    以下のメソッドを実装する必要がある。
    """

    def __init__(self, config: EmbeddingProviderConfig):
        self.config = config
        self._initialized = False

    @property
    @abstractmethod
    def provider_type(self) -> EmbeddingProviderType:
        """プロバイダータイプを返す"""
        pass

    @property
    @abstractmethod
    def vector_size(self) -> int:
        """埋め込みベクトルの次元数を返す"""
        pass

    @abstractmethod
    async def initialize(self) -> None:
        """
        プロバイダーの初期化処理
        認証情報の検証やクライアントの初期化を行う
        """
        pass

    @abstractmethod
    async def embed_text(self, text: str) -> Optional[List[float]]:
        """
        単一テキストの埋め込みベクトルを取得

        Args:
            text: 埋め込むテキスト

        Returns:
            埋め込みベクトル（失敗時はNone）
        """
        pass

    @abstractmethod
    async def embed_texts(self, texts: List[str]) -> Optional[List[List[float]]]:
        """
        複数テキストの埋め込みベクトルを一括取得

        Args:
            texts: 埋め込むテキストのリスト

        Returns:
            埋め込みベクトルのリスト（失敗時はNone）
        """
        pass

    async def health_check(self) -> bool:
        """
        プロバイダーの健全性チェック

        Returns:
            True: 正常に動作している
            False: 問題がある
        """
        try:
            await self.initialize()
            # 簡単なテスト埋め込みを実行
            result = await self.embed_text("test")
            return result is not None
        except Exception:
            return False

    def get_model_info(self) -> dict:
        """モデル情報を取得"""
        return {
            "provider": self.provider_type.value,
            "model": self.config.model,
            "vector_size": self.vector_size,
        }
