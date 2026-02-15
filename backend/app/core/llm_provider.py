"""
PLURA - LLM Provider Abstract Interface
マルチプロバイダー対応のための抽象インターフェース
"""
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, List, Optional, Type, TypeVar

from pydantic import BaseModel


class LLMUsageRole(str, Enum):
    """LLM使用用途のロール定義"""
    FAST = "fast"          # リアルタイム解析用（低レイテンシ優先）
    BALANCED = "balanced"  # 標準的な処理用（バランス重視）
    DEEP = "deep"          # 深い洞察・構造化用（品質優先）


class ProviderType(str, Enum):
    """サポートするプロバイダータイプ"""
    OPENAI = "openai"
    VERTEX = "vertex"


T = TypeVar("T", bound=BaseModel)


class LLMProviderConfig(BaseModel):
    """プロバイダー設定"""
    provider: ProviderType
    model: str
    temperature: Optional[float] = 0.3
    max_tokens: Optional[int] = None


class LLMResponse(BaseModel):
    """LLMレスポンスのラッパー"""
    content: str
    model: str
    provider: ProviderType
    usage: Optional[Dict[str, int]] = None
    raw_response: Optional[Dict[str, Any]] = None


class LLMProvider(ABC):
    """
    LLMプロバイダーの抽象基底クラス

    全てのプロバイダー実装はこのクラスを継承し、
    以下のメソッドを実装する必要がある。
    """

    def __init__(self, config: LLMProviderConfig):
        self.config = config
        self._initialized = False

    @property
    @abstractmethod
    def provider_type(self) -> ProviderType:
        """プロバイダータイプを返す"""
        pass

    @abstractmethod
    async def initialize(self) -> None:
        """
        プロバイダーの初期化処理
        認証情報の検証やクライアントの初期化を行う
        """
        pass

    @abstractmethod
    async def generate_text(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        """
        テキスト生成

        Args:
            messages: チャットメッセージのリスト [{"role": "...", "content": "..."}]
            temperature: 温度パラメータ（指定がなければconfigの値を使用）
            max_tokens: 最大トークン数

        Returns:
            LLMResponse: 生成されたテキストを含むレスポンス
        """
        pass

    @abstractmethod
    async def generate_structured_output(
        self,
        messages: List[Dict[str, str]],
        response_model: Type[T],
        temperature: Optional[float] = None,
    ) -> T:
        """
        構造化出力の生成（Pydanticモデル対応）

        Args:
            messages: チャットメッセージのリスト
            response_model: 期待するレスポンスのPydanticモデル
            temperature: 温度パラメータ

        Returns:
            response_model型のインスタンス
        """
        pass

    async def generate_json(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        JSON形式での出力生成

        デフォルト実装はgenerate_textの結果をJSONとしてパースする。
        プロバイダーがネイティブでJSON modeをサポートする場合はオーバーライド可能。

        Args:
            messages: チャットメッセージのリスト
            temperature: 温度パラメータ

        Returns:
            パースされたJSONオブジェクト
        """
        import json
        response = await self.generate_text(messages, temperature)
        return json.loads(response.content)

    def is_reasoning_model(self) -> bool:
        """
        現在のモデルがreasoningモデルかどうかを判定

        reasoningモデルは以下の特性を持つ:
        - JSON modeをサポートしない
        - temperatureパラメータをサポートしない場合がある
        """
        import re
        reasoning_patterns = [
            r"^o1",           # o1-preview, o1-mini
            r"^gpt-5",        # gpt-5.x系
            r"reasoning",     # reasoningが含まれるモデル
        ]
        for pattern in reasoning_patterns:
            if re.search(pattern, self.config.model, re.IGNORECASE):
                return True
        return False

    def get_model_info(self) -> Dict[str, Any]:
        """モデル情報を取得"""
        return {
            "provider": self.provider_type.value,
            "model": self.config.model,
            "is_reasoning": self.is_reasoning_model(),
        }

    async def health_check(self) -> bool:
        """
        プロバイダーの健全性チェック

        Returns:
            True: 正常に動作している
            False: 問題がある
        """
        try:
            await self.initialize()
            return True
        except Exception:
            return False
