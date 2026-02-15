"""
PLURA - OpenAI Provider
OpenAI APIを使用するLLMプロバイダー実装
"""
import json
import re
from typing import Any, Dict, List, Optional, Type, TypeVar

from openai import AsyncOpenAI
from pydantic import BaseModel

from app.core.llm_provider import (
    LLMProvider,
    LLMProviderConfig,
    LLMResponse,
    ProviderType,
)


T = TypeVar("T", bound=BaseModel)


def extract_json_from_text(text: str) -> Optional[Dict[str, Any]]:
    """
    テキストからJSONを抽出
    reasoningモデルはJSON modeをサポートしないため、
    テキスト出力からJSONを抽出する必要がある
    """
    # まず、テキスト全体がJSONかどうかを試す
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass

    # コードブロック内のJSONを探す
    json_patterns = [
        r"```json\s*([\s\S]*?)\s*```",  # ```json ... ```
        r"```\s*([\s\S]*?)\s*```",       # ``` ... ```
        r"\{[\s\S]*\}",                   # { ... } (最外のJSONオブジェクト)
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


class OpenAIProvider(LLMProvider):
    """
    OpenAI APIを使用するLLMプロバイダー

    特徴:
    - AsyncOpenAIクライアントによる非同期処理
    - JSON modeサポート（非reasoningモデル）
    - reasoningモデル（o1, gpt-5系）の特別処理
    """

    def __init__(self, config: LLMProviderConfig, api_key: Optional[str] = None):
        super().__init__(config)
        self._api_key = api_key
        self._client: Optional[AsyncOpenAI] = None

    @property
    def provider_type(self) -> ProviderType:
        return ProviderType.OPENAI

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

    async def generate_text(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        """テキスト生成"""
        await self.initialize()

        kwargs: Dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
        }

        # reasoningモデルはtemperatureをサポートしない
        if not self.is_reasoning_model():
            kwargs["temperature"] = temperature or self.config.temperature

        if max_tokens:
            kwargs["max_tokens"] = max_tokens
        elif self.config.max_tokens:
            kwargs["max_tokens"] = self.config.max_tokens

        response = await self.client.chat.completions.create(**kwargs)
        content = response.choices[0].message.content or ""

        usage = None
        if response.usage:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }

        return LLMResponse(
            content=content,
            model=self.config.model,
            provider=self.provider_type,
            usage=usage,
        )

    async def generate_json(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
    ) -> Dict[str, Any]:
        """JSON形式での出力生成"""
        await self.initialize()

        kwargs: Dict[str, Any] = {
            "model": self.config.model,
            "messages": messages.copy(),  # メッセージを変更する可能性があるのでコピー
        }

        if self.is_reasoning_model():
            # reasoningモデルはJSON modeをサポートしないため、
            # プロンプトでJSON出力を指示
            for msg in kwargs["messages"]:
                if msg.get("role") == "system":
                    msg["content"] += "\n\n必ず有効なJSON形式で回答してください。"
                    break
        else:
            # 通常のモデルはJSON modeを使用
            kwargs["temperature"] = temperature or self.config.temperature
            kwargs["response_format"] = {"type": "json_object"}

        response = await self.client.chat.completions.create(**kwargs)
        content = response.choices[0].message.content or ""

        if self.is_reasoning_model():
            # reasoningモデルの場合はテキストからJSONを抽出
            result = extract_json_from_text(content)
            if result is None:
                raise ValueError(f"Failed to extract JSON from response: {content[:200]}...")
            return result
        else:
            return json.loads(content)

    async def generate_structured_output(
        self,
        messages: List[Dict[str, str]],
        response_model: Type[T],
        temperature: Optional[float] = None,
    ) -> T:
        """
        構造化出力の生成（Pydanticモデル対応）

        OpenAIのstructured outputs機能を使用するか、
        JSON modeでの出力をPydanticモデルに変換する。
        """
        # Pydanticモデルのスキーマを取得してプロンプトに追加
        schema = response_model.model_json_schema()
        schema_instruction = f"\n\nレスポンスは以下のJSONスキーマに従ってください:\n{json.dumps(schema, ensure_ascii=False, indent=2)}"

        # システムメッセージにスキーマ情報を追加
        augmented_messages = []
        for msg in messages:
            if msg.get("role") == "system":
                augmented_messages.append({
                    "role": "system",
                    "content": msg["content"] + schema_instruction,
                })
            else:
                augmented_messages.append(msg)

        # JSON出力を生成
        result = await self.generate_json(augmented_messages, temperature)

        # Pydanticモデルにパース
        return response_model.model_validate(result)
