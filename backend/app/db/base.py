"""
PLURA - Database Base
SQLAlchemy基盤設定
"""
from datetime import datetime, timezone
from typing import AsyncGenerator

from sqlalchemy import MetaData
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

# 命名規則の設定
convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=convention)


class Base(DeclarativeBase):
    """すべてのモデルの基底クラス"""

    metadata = metadata


# エンジン作成用の引数を動的に構築
engine_kwargs = {
    "echo": False,  # または settings.debug
}

# SQLite以外（PostgreSQL等）の場合のみ、プーリング設定を追加
if not settings.database_url.startswith("sqlite"):
    engine_kwargs["pool_size"] = settings.database_pool_size
    engine_kwargs["max_overflow"] = settings.database_max_overflow

# 非同期エンジン
engine = create_async_engine(
    settings.database_url,
    **engine_kwargs
)

# 非同期セッションファクトリ
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """非同期セッションを取得するジェネレータ"""
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()


def utc_now() -> datetime:
    """現在のUTC時刻を取得"""
    return datetime.now(timezone.utc)
