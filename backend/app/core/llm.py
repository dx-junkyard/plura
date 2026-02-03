"""
MINDYARD - LLM Utilities
LLMモデル選択とreasoning対応のユーティリティ
"""
import json
import re
from enum import Enum
from typing import Any, Dict, List, Optional

from openai import AsyncOpenAI

from app.core.config import settings


class ModelTier(str, Enum):
    """モデルの選択パターン"""
    DEEP = "deep"        # 深い思考が必要な複雑なタスク用
    BALANCED = "balanced"  # バランスの取れた処理用
    FAST = "fast"        # 素早いレスポンスが必要なタスク用


# Reasoningモデルのパターン（これらはJSON modeをサポートしない）
REASONING_MODEL_PATTERNS = [
    r"^o1",           # o1-preview, o1-mini
    r"^gpt-5",        # gpt-5.2, gpt-5-mini など（仮定）
    r"reasoning",     # reasoning が含まれるモデル名
]


def get_model_name(tier: ModelTier) -> str:
    """指定されたティアのモデル名を取得"""
    model_map = {
        ModelTier.DEEP: settings.llm_model_deep,
        ModelTier.BALANCED: settings.llm_model_balanced,
        ModelTier.FAST: settings.llm_model_fast,
    }
    return model_map.get(tier, settings.llm_model_balanced)


def is_reasoning_model(model_name: str) -> bool:
    """モデルがreasoningモデルかどうかを判定"""
    for pattern in REASONING_MODEL_PATTERNS:
        if re.search(pattern, model_name, re.IGNORECASE):
            return True
    return False


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
                # マッチした部分がJSONとしてパースできるか確認
                if isinstance(match, str):
                    # 最後のパターンの場合、全体がマッチしている
                    json_str = match if pattern == r"\{[\s\S]*\}" else match
                    return json.loads(json_str.strip())
            except json.JSONDecodeError:
                continue

    return None


class LLMClient:
    """
    LLMクライアント
    モデルティアに応じた設定とreasoning対応を提供
    """

    def __init__(self, tier: ModelTier = ModelTier.BALANCED):
        self.tier = tier
        self.model = get_model_name(tier)
        self.is_reasoning = is_reasoning_model(self.model)
        self._client: Optional[AsyncOpenAI] = None

    @property
    def client(self) -> AsyncOpenAI:
        """OpenAIクライアントの遅延初期化"""
        if self._client is None:
            if not settings.openai_api_key:
                raise ValueError("OpenAI API key is not configured")
            self._client = AsyncOpenAI(api_key=settings.openai_api_key)
        return self._client

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        json_response: bool = True,
    ) -> Dict[str, Any]:
        """
        チャット補完を実行

        Args:
            messages: メッセージのリスト
            temperature: 温度パラメータ（reasoningモデルでは無視される）
            json_response: JSONレスポンスを期待するかどうか

        Returns:
            パースされたレスポンス（json_response=Trueの場合）またはテキスト
        """
        # reasoningモデルの場合の調整
        kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
        }

        if self.is_reasoning:
            # reasoningモデルはtemperatureをサポートしないことが多い
            # JSON modeもサポートしないため、プロンプトでJSON出力を指示
            if json_response:
                # システムプロンプトにJSON出力の指示を追加
                for msg in messages:
                    if msg.get("role") == "system":
                        msg["content"] += "\n\n必ず有効なJSON形式で回答してください。"
                        break
        else:
            # 通常のモデル
            kwargs["temperature"] = temperature
            if json_response:
                kwargs["response_format"] = {"type": "json_object"}

        response = await self.client.chat.completions.create(**kwargs)
        content = response.choices[0].message.content

        if json_response:
            # JSONをパース
            if self.is_reasoning:
                # reasoningモデルの場合はテキストからJSONを抽出
                result = extract_json_from_text(content)
                if result is None:
                    raise ValueError(f"Failed to extract JSON from response: {content[:200]}...")
                return result
            else:
                return json.loads(content)

        return {"content": content}

    def get_model_info(self) -> Dict[str, Any]:
        """モデル情報を取得"""
        return {
            "tier": self.tier.value,
            "model": self.model,
            "is_reasoning": self.is_reasoning,
        }


# 各ティアのクライアントインスタンスを作成するファクトリ関数
def create_llm_client(tier: ModelTier) -> LLMClient:
    """指定されたティアのLLMクライアントを作成"""
    return LLMClient(tier=tier)
