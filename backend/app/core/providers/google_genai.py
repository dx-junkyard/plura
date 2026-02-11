"""
MINDYARD - Google Gen AI Provider
Google Gen AI SDK (google-genai) を使用するLLMプロバイダー実装
"""
import json
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
from app.core.logger import get_traced_logger


logger = get_traced_logger("GoogleGenAI")

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

        logger.info(
            "Initializing Google Gen AI client",
            metadata={
                "project_id": self._project_id,
                "location": self._location,
                "model": self.config.model,
            },
        )

        if not self._project_id:
            logger.error(
                "GOOGLE_CLOUD_PROJECT is not set. "
                "Google Gen AI provider requires a GCP project ID.",
                metadata={"project_id": self._project_id},
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
            logger.info(
                "Google Gen AI client initialized successfully",
                metadata={
                    "project_id": self._project_id,
                    "location": self._location,
                    "client_type": type(self._client).__name__,
                },
            )

        except Exception as e:
            logger.exception(
                "Failed to initialize Google Gen AI client",
                metadata={
                    "error_type": type(e).__name__,
                    "error": str(e),
                    "project_id": self._project_id,
                    "location": self._location,
                },
            )
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
        logger.info(
            "generate_text called",
            metadata={
                "model": self.config.model,
                "message_count": len(messages),
                "temperature": temperature,
            },
        )
        try:
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

            logger.info(
                "generate_text completed",
                metadata={
                    "model": self.config.model,
                    "content_length": len(content),
                    "usage": usage,
                },
            )

            return LLMResponse(
                content=content,
                model=self.config.model,
                provider=self.provider_type,
                usage=usage,
            )
        except Exception as e:
            logger.exception(
                "generate_text FAILED",
                metadata={
                    "error_type": type(e).__name__,
                    "error": str(e),
                    "model": self.config.model,
                },
            )
            raise

    async def generate_json(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
    ) -> Dict[str, Any]:
        """JSON形式での出力生成"""
        logger.info(
            "generate_json called",
            metadata={
                "model": self.config.model,
                "message_count": len(messages),
                "temperature": temperature,
            },
        )
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
            response = await self.client.aio.models.generate_content(
                model=self.config.model,
                contents=contents,
                config=config,
            )
            content = response.text if response.text else "{}"
            parsed = json.loads(content)
            logger.info(
                "generate_json completed (JSON mode)",
                metadata={
                    "model": self.config.model,
                    "content_length": len(content),
                },
            )
            return parsed

        except Exception as e:
            logger.warning(
                "generate_json JSON mode failed, falling back to text extraction",
                metadata={
                    "error_type": type(e).__name__,
                    "error": str(e),
                    "model": self.config.model,
                },
            )
            # JSON modeが失敗した場合、通常のテキスト生成でJSON抽出を試みる
            try:
                config = types.GenerateContentConfig(
                    temperature=temperature or self.config.temperature,
                    system_instruction=system_instruction,
                )
                response = await self.client.aio.models.generate_content(
                    model=self.config.model,
                    contents=contents,
                    config=config,
                )
                content = response.text if response.text else ""
                result = extract_json_from_text(content)
                if result is None:
                    raise ValueError(f"Failed to extract JSON from response: {content[:200]}...")
                logger.info(
                    "generate_json completed (text extraction fallback)",
                    metadata={
                        "model": self.config.model,
                        "content_length": len(content),
                    },
                )
                return result
            except Exception as fallback_e:
                logger.exception(
                    "generate_json FAILED (both JSON mode and text extraction)",
                    metadata={
                        "original_error_type": type(e).__name__,
                        "original_error": str(e),
                        "fallback_error_type": type(fallback_e).__name__,
                        "fallback_error": str(fallback_e),
                        "model": self.config.model,
                    },
                )
                raise

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
        logger.info(
            "generate_structured_output called",
            metadata={
                "model": self.config.model,
                "response_model": response_model.__name__,
                "message_count": len(messages),
            },
        )
        await self.initialize()

        system_instruction, contents = self._convert_messages_to_gemini_format(messages)

        config = types.GenerateContentConfig(
            temperature=temperature or self.config.temperature,
            response_mime_type="application/json",
            response_schema=response_model,
            system_instruction=system_instruction,
        )

        try:
            response = await self.client.aio.models.generate_content(
                model=self.config.model,
                contents=contents,
                config=config,
            )
            content = response.text if response.text else "{}"
            data = json.loads(content)
            logger.info(
                "generate_structured_output completed (schema mode)",
                metadata={"model": self.config.model},
            )
            return response_model.model_validate(data)

        except Exception as e:
            logger.warning(
                "generate_structured_output schema mode failed, falling back to generate_json",
                metadata={
                    "error_type": type(e).__name__,
                    "error": str(e),
                    "model": self.config.model,
                },
            )
            try:
                result = await self.generate_json(messages, temperature)
                return response_model.model_validate(result)
            except Exception as fallback_e:
                logger.exception(
                    "generate_structured_output FAILED (both schema and JSON fallback)",
                    metadata={
                        "original_error_type": type(e).__name__,
                        "original_error": str(e),
                        "fallback_error_type": type(fallback_e).__name__,
                        "fallback_error": str(fallback_e),
                        "model": self.config.model,
                    },
                )
                raise

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
