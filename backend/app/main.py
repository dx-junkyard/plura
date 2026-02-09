"""
MINDYARD - FastAPI Application
メインアプリケーションエントリーポイント
"""
from contextlib import asynccontextmanager
import time

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
import structlog

from app.core.config import settings
from app.core.trace_context import generate_trace_id, get_trace_id
from app.core.logger import get_traced_logger
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

# --- Trace ID Middleware ---
_request_logger = get_traced_logger("Main")


class TraceIDMiddleware(BaseHTTPMiddleware):
    """リクエストごとに trace_id を生成し、レスポンスヘッダーに付与する"""

    async def dispatch(self, request: Request, call_next):
        trace_id = generate_trace_id()
        start = time.monotonic()

        _request_logger.info(
            "Request received",
            metadata={
                "method": request.method,
                "path": request.url.path,
            },
        )

        response: Response = await call_next(request)

        duration_ms = round((time.monotonic() - start) * 1000, 1)
        response.headers["X-Trace-ID"] = trace_id

        _request_logger.info(
            "Response sent",
            metadata={
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            },
        )

        return response


# CORS設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.backend_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Trace ID Middleware（CORSより内側に配置）
app.add_middleware(TraceIDMiddleware)

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
