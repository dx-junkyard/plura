"""
MINDYARD - FastAPI Application
メインアプリケーションエントリーポイント
"""
import logging
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
py_logger = logging.getLogger("mindyard.app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """アプリケーションのライフサイクル管理"""
    logger.info("Starting MINDYARD application", version=settings.app_version)
    py_logger.info(f"[CORS] Configured allow_origins: {settings.backend_cors_origins}")

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


# CORSデバッグ用 Pure ASGI Middleware（BaseHTTPMiddlewareを避ける）
class CORSDebugMiddleware:
    """CORS のデバッグ用ミドルウェア: リクエストの Origin と レスポンスの CORS ヘッダーをログ出力"""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        method = scope.get("method", "")

        # /api/ パスのリクエストのみデバッグログ
        if "/api/" not in path:
            await self.app(scope, receive, send)
            return

        # Origin ヘッダーを取得
        headers = dict(scope.get("headers", []))
        origin = headers.get(b"origin", b"(none)").decode("utf-8", errors="replace")
        py_logger.info(f"[CORS-Debug] {method} {path} | Origin: {origin}")

        # レスポンスのヘッダーをキャプチャ
        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                resp_headers = dict(message.get("headers", []))
                acao = resp_headers.get(
                    b"access-control-allow-origin", b"(missing)"
                ).decode("utf-8", errors="replace")
                status = message.get("status", "?")
                py_logger.info(
                    f"[CORS-Debug] {method} {path} -> {status} | "
                    f"ACAO: {acao}"
                )
            await send(message)

        await self.app(scope, receive, send_wrapper)


# ミドルウェアは後に追加したものが外側になる
# CORSMiddleware → CORSDebugMiddleware の順（CORS処理後のヘッダーを確認する）
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.backend_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(CORSDebugMiddleware)

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
    from app.core.llm import llm_manager
    from app.core.llm_provider import LLMUsageRole
    from app.core.embedding import embedding_manager

    llm_providers = {}
    for role in LLMUsageRole:
        config = settings.get_llm_config(role.value)
        llm_providers[role.value] = {
            "provider": config.get("provider"),
            "model": config.get("model"),
        }

    embedding_config = settings.get_embedding_config()

    return {
        "status": "healthy",
        "version": settings.app_version,
        "providers": {
            "llm": llm_providers,
            "embedding": {
                "provider": embedding_config.get("provider"),
                "model": embedding_config.get("model"),
            },
            "vertex_available": settings.is_vertex_available(),
            "openai_available": settings.is_openai_available(),
        },
    }
