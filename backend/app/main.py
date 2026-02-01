"""
MINDYARD - FastAPI Application
メインアプリケーションエントリーポイント
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import structlog

from app.core.config import settings
from app.api.v1.router import api_router
from app.db.base import engine, Base

# ロギング設定
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """アプリケーションのライフサイクル管理"""
    logger.info("Starting MINDYARD application", version=settings.app_version)

    # データベーステーブルの作成（開発用）
    if settings.environment == "development":
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables created")

    yield

    logger.info("Shutting down MINDYARD application")


# FastAPIアプリケーション
app = FastAPI(
    title=settings.app_name,
    description="""
    MINDYARD: 自分だけのノートから、みんなの集合知へ

    個人が自分のために行う「記録（Log）」を、
    組織全体の「集合知（Wisdom of Crowds）」へと自然に変換する
    ナレッジ共創プラットフォーム
    """,
    version=settings.app_version,
    openapi_url=f"{settings.api_v1_prefix}/openapi.json",
    docs_url=f"{settings.api_v1_prefix}/docs",
    redoc_url=f"{settings.api_v1_prefix}/redoc",
    lifespan=lifespan,
)

# CORS設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# APIルーターの登録
app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.get("/")
async def root():
    """ルートエンドポイント"""
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "description": "Knowledge co-creation platform",
        "docs": f"{settings.api_v1_prefix}/docs",
    }


@app.get("/health")
async def health_check():
    """ヘルスチェックエンドポイント"""
    return {
        "status": "healthy",
        "version": settings.app_version,
    }
