"""
MINDYARD - Google Gen AI Provider
Google Gen AI SDK (google-genai) を使用するLLMプロバイダー実装
"""
import json
import logging
import re
from typing import Any, Dict, List, Optional, Type, TypeVar

from pydantic import BaseModel
from google import genai
from google.genai import types

from app.core.llm_provider import (
    LLMProvider,
    LLMProviderConfig,
    LLMResponse,
    ProviderType,
)


logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


def extract_json_from_text(text: str) -> Optional[Dict[str, Any]]:
    """テキストからJSONを抽出"""
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


class GoogleGenAIClient(LLMProvider):
    """
    Google Gen AI SDK を使用するLLMプロバイダー

    特徴:
    - google-genai SDK によるVertex AI経由のGeminiモデルアクセス
    - GOOGLE_CLOUD_PROJECT 環境変数によるプロジェクト指定
    - Fail Fast: 必要な環境変数が不足している場合は起動時にエラー
    - 構造化出力のネイティブサポート
    """

    def __init__(
        self,
        config: LLMProviderConfig,
        project_id: Optional[str] = None,
        location: str = "us-central1",
    ):
        super().__init__(config)
        self._project_id = project_id
        self._location = location
        self._client: Optional[genai.Client] = None

    @property
    def provider_type(self) -> ProviderType:
        return ProviderType.VERTEX

    async def initialize(self) -> None:
        """Google Gen AI クライアントを初期化（Fail Fast）"""
        if self._initialized:
            return

        if not self._project_id:
            logger.critical(
                "GOOGLE_CLOUD_PROJECT is not set. "
                "Google Gen AI provider requires a GCP project ID. "
                "Set the GOOGLE_CLOUD_PROJECT environment variable."
            )
            raise ValueError(
                "GOOGLE_CLOUD_PROJECT is not set. "
                "Cannot initialize Google Gen AI provider without a GCP project ID."
            )

        try:
            self._client = genai.Client(
                vertexai=True,
                project=self._project_id,
                location=self._location,
            )
            self._initialized = True

        except Exception as e:
            logger.critical(f"Failed to initialize Google Gen AI client: {e}")
            raise RuntimeError(f"Failed to initialize Google Gen AI: {e}")

    @property
    def client(self) -> genai.Client:
        """初期化済みクライアントを取得"""
        if self._client is None:
            raise RuntimeError("Provider not initialized. Call initialize() first.")
        return self._client

    def _convert_messages_to_gemini_format(
        self, messages: List[Dict[str, str]]
    ) -> tuple[Optional[str], List[types.Content]]:
        """
        OpenAI形式のメッセージをGemini形式に変換

        Returns:
            (system_instruction, contents)
        """
        system_instruction = None
        contents = []

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            if role == "system":
                system_instruction = content
            elif role == "assistant":
                contents.append(types.Content(
                    role="model",
                    parts=[types.Part(text=content)],
                ))
            else:  # user
                contents.append(types.Content(
                    role="user",
                    parts=[types.Part(text=content)],
                ))

        return system_instruction, contents

    async def generate_text(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        """テキスト生成"""
        await self.initialize()

        system_instruction, contents = self._convert_messages_to_gemini_format(messages)

        config = types.GenerateContentConfig(
            temperature=temperature or self.config.temperature,
            max_output_tokens=max_tokens or self.config.max_tokens,
            system_instruction=system_instruction,
        )

        response = await self.client.aio.models.generate_content(
            model=self.config.model,
            contents=contents,
            config=config,
        )

        content = response.text if response.text else ""

        usage = None
        if response.usage_metadata:
            usage = {
                "prompt_tokens": response.usage_metadata.prompt_token_count,
                "completion_tokens": response.usage_metadata.candidates_token_count,
                "total_tokens": response.usage_metadata.total_token_count,
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

        system_instruction, contents = self._convert_messages_to_gemini_format(messages)

        # JSON出力の指示を追加
        if system_instruction:
            system_instruction += "\n\n必ず有効なJSON形式で回答してください。余計なテキストは含めないでください。"
        else:
            system_instruction = "必ず有効なJSON形式で回答してください。余計なテキストは含めないでください。"

        config = types.GenerateContentConfig(
            temperature=temperature or self.config.temperature,
            response_mime_type="application/json",
            system_instruction=system_instruction,
        )

        try:
            response = await self.client.models.generate_content_async(
                model=self.config.model,
                contents=contents,
                config=config,
            )
            content = response.text if response.text else "{}"
            return json.loads(content)

        except Exception:
            # JSON modeが失敗した場合、通常のテキスト生成でJSON抽出を試みる
            config = types.GenerateContentConfig(
                temperature=temperature or self.config.temperature,
                system_instruction=system_instruction,
            )
            response = await self.client.models.generate_content_async(
                model=self.config.model,
                contents=contents,
                config=config,
            )
            content = response.text if response.text else ""
            result = extract_json_from_text(content)
            if result is None:
                raise ValueError(f"Failed to extract JSON from response: {content[:200]}...")
            return result

    async def generate_structured_output(
        self,
        messages: List[Dict[str, str]],
        response_model: Type[T],
        temperature: Optional[float] = None,
    ) -> T:
        """
        構造化出力の生成（Pydanticモデル対応）

        Geminiのresponse_schemaを使用して構造化出力を生成。
        """
        await self.initialize()

        system_instruction, contents = self._convert_messages_to_gemini_format(messages)

        config = types.GenerateContentConfig(
            temperature=temperature or self.config.temperature,
            response_mime_type="application/json",
            response_schema=response_model,
            system_instruction=system_instruction,
        )

        try:
            response = await self.client.models.generate_content_async(
                model=self.config.model,
                contents=contents,
                config=config,
            )
            content = response.text if response.text else "{}"
            data = json.loads(content)
            return response_model.model_validate(data)

        except Exception:
            # フォールバック: 通常のJSON生成
            result = await self.generate_json(messages, temperature)
            return response_model.model_validate(result)

    def is_reasoning_model(self) -> bool:
        """
        Geminiモデルがreasoningモデルかどうかを判定

        現時点ではGeminiはreasoningモデルとして扱わない。
        将来的にGemini系がreasoningをサポートする場合は更新。
        """
        reasoning_patterns = [
            r"gemini.*thinking",
            r"gemini.*reasoning",
        ]
        for pattern in reasoning_patterns:
            if re.search(pattern, self.config.model, re.IGNORECASE):
                return True
        return False
