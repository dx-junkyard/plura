"""
MINDYARD - Core Configuration
システム全体の設定を管理
"""
import json
from functools import lru_cache
from typing import Any, Dict, List, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# デフォルトのLLM設定
DEFAULT_LLM_CONFIG_FAST = {"provider": "openai", "model": "gpt-5-nano"}
DEFAULT_LLM_CONFIG_BALANCED = {"provider": "openai", "model": "gpt-5-mini"}
DEFAULT_LLM_CONFIG_DEEP = {"provider": "openai", "model": "gpt-5.2"}

# デフォルトのEmbedding設定
DEFAULT_EMBEDDING_CONFIG = {"provider": "openai", "model": "text-embedding-3-small"}


class Settings(BaseSettings):
    """アプリケーション設定"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Application
    app_name: str = "MINDYARD"
    app_version: str = "0.1.0"
    debug: bool = False
    environment: str = "development"

    # API
    api_v1_prefix: str = "/api/v1"

    # Security
    secret_key: str = Field(default="change-me-in-production-mindyard-secret-key-2024")
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7  # 7 days

    # Database
    database_url: str = Field(
        default="postgresql+asyncpg://mindyard:mindyard@localhost:5432/mindyard"
    )
    database_pool_size: int = 20
    database_max_overflow: int = 10

    # Redis
    redis_url: str = Field(default="redis://localhost:6379/0")

    # Qdrant Vector Database
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_collection_name: str = "mindyard_insights"

    # OpenAI
    openai_api_key: Optional[str] = None

    # Google Cloud
    google_cloud_project: Optional[str] = None  # GOOGLE_CLOUD_PROJECT env var
    google_application_credentials: Optional[str] = None  # ADC credentials path

    # Embedding Configuration (Multi-Provider, JSON format)
    # 例: EMBEDDING_CONFIG='{"provider": "openai", "model": "text-embedding-3-small"}'
    # 例: EMBEDDING_CONFIG='{"provider": "vertex", "model": "text-embedding-004"}'
    embedding_config: str = Field(
        default=json.dumps(DEFAULT_EMBEDDING_CONFIG),
        description="Embedding provider config (JSON string)"
    )

    # Legacy embedding model (deprecated, use embedding_config instead)
    openai_embedding_model: str = "text-embedding-3-small"

    # LLM Configuration (Multi-Provider, JSON format)
    # 環境変数でJSON文字列として設定可能
    # 例: LLM_CONFIG_FAST='{"provider": "openai", "model": "gpt-5-nano"}'
    # 例: LLM_CONFIG_BALANCED='{"provider": "vertex", "model": "gemini-1.5-flash"}'
    llm_config_fast: str = Field(
        default=json.dumps(DEFAULT_LLM_CONFIG_FAST),
        description="FAST tier LLM config (JSON string)"
    )
    llm_config_balanced: str = Field(
        default=json.dumps(DEFAULT_LLM_CONFIG_BALANCED),
        description="BALANCED tier LLM config (JSON string)"
    )
    llm_config_deep: str = Field(
        default=json.dumps(DEFAULT_LLM_CONFIG_DEEP),
        description="DEEP tier LLM config (JSON string)"
    )

    # Legacy LLM Model Configuration (deprecated, use llm_config_* instead)
    # 後方互換性のために残す
    llm_model_deep: str = "gpt-5.2"
    llm_model_balanced: str = "gpt-5-mini"
    llm_model_fast: str = "gpt-5-nano"
    openai_model: str = "gpt-4-turbo-preview"

    # Celery
    celery_broker_url: str = Field(default="redis://localhost:6379/1")
    celery_result_backend: str = Field(default="redis://localhost:6379/2")

    # Layer 2 Processing
    sharing_threshold_score: int = 80  # 共有推奨の閾値（この値以上で PENDING_APPROVAL）

    # CORS
    backend_cors_origins: List[str] = ["http://localhost:3000", "http://localhost:8000"]

    @field_validator("backend_cors_origins", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Any) -> List[str]:
        if isinstance(v, str):
            # Try JSON list first: '["http://localhost:3000", "https://example.com"]'
            if v.startswith("["):
                try:
                    parsed = json.loads(v)
                    if isinstance(parsed, list):
                        return [str(item).strip().rstrip("/") for item in parsed]
                except json.JSONDecodeError:
                    pass
            # Fall back to comma-separated: "http://localhost:3000,https://example.com"
            return [origin.strip().rstrip("/") for origin in v.split(",") if origin.strip()]
        if isinstance(v, list):
            return [str(item).strip().rstrip("/") for item in v]
        return v

    # Logging
    log_level: str = "INFO"

    def get_llm_config(self, role: str) -> Dict[str, Any]:
        """
        用途別のLLM設定を取得

        Args:
            role: "fast", "balanced", or "deep"

        Returns:
            {"provider": "openai"|"vertex", "model": "model-name", ...}
        """
        config_map = {
            "fast": self.llm_config_fast,
            "balanced": self.llm_config_balanced,
            "deep": self.llm_config_deep,
        }

        config_str = config_map.get(role, self.llm_config_balanced)

        try:
            config = json.loads(config_str)
        except json.JSONDecodeError:
            # パースに失敗した場合はデフォルト設定を返す
            defaults = {
                "fast": DEFAULT_LLM_CONFIG_FAST,
                "balanced": DEFAULT_LLM_CONFIG_BALANCED,
                "deep": DEFAULT_LLM_CONFIG_DEEP,
            }
            config = defaults.get(role, DEFAULT_LLM_CONFIG_BALANCED)

        return config

    def get_embedding_config(self) -> Dict[str, Any]:
        """
        Embedding設定を取得

        Returns:
            {"provider": "openai"|"vertex", "model": "model-name", ...}
        """
        try:
            config = json.loads(self.embedding_config)
        except json.JSONDecodeError:
            config = DEFAULT_EMBEDDING_CONFIG
        return config

    def is_openai_available(self) -> bool:
        """OpenAI APIが利用可能かどうか"""
        return bool(self.openai_api_key)

    def is_google_genai_available(self) -> bool:
        """Google Gen AI (Gemini) が利用可能かどうか"""
        return bool(self.google_cloud_project)


@lru_cache
def get_settings() -> Settings:
    """設定のシングルトンインスタンスを取得"""
    return Settings()


settings = get_settings()
