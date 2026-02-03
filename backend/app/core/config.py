"""
MINDYARD - Core Configuration
システム全体の設定を管理
"""
from functools import lru_cache
from typing import List, Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    openai_embedding_model: str = "text-embedding-3-small"

    # LLM Model Configuration (3 patterns)
    # Deep: 深い思考が必要な複雑なタスク用（reasoning model）
    llm_model_deep: str = "gpt-5.2"
    # Balanced: バランスの取れた処理用
    llm_model_balanced: str = "gpt-5-mini"
    # Fast: 素早いレスポンスが必要なタスク用
    llm_model_fast: str = "gpt-5-nano"

    # Legacy support (deprecated, use llm_model_* instead)
    openai_model: str = "gpt-4-turbo-preview"

    # Celery
    celery_broker_url: str = Field(default="redis://localhost:6379/1")
    celery_result_backend: str = Field(default="redis://localhost:6379/2")

    # Layer 2 Processing
    sharing_threshold_score: int = 70  # 共有価値スコアの閾値

    # CORS
    cors_origins: List[str] = ["http://localhost:3000", "http://localhost:8000"]

    # Logging
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    """設定のシングルトンインスタンスを取得"""
    return Settings()


settings = get_settings()
