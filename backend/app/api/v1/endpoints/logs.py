"""
MINDYARD - Log Endpoints
Layer 1: Private Logger API
"""
from datetime import datetime
from typing import Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.base import get_async_session
from app.models.user import User
from app.models.raw_log import RawLog
from app.schemas.raw_log import (
    RawLogCreate,
    RawLogResponse,
    RawLogListResponse,
    AckResponse,
)
from app.services.layer1.context_analyzer import context_analyzer
from app.workers.tasks import analyze_log_structure

router = APIRouter()


@router.post("/", response_model=AckResponse, status_code=status.HTTP_201_CREATED)
async def create_log(
    log_in: RawLogCreate,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
):
    """
    新しいログを作成

    ノン・ジャッジメンタル応答:
    AIは「回答」や「アドバイス」を行わない。
    「聞く」ことに徹し、受容的な相槌（Ack）のみを返す。
    """
    # ログの作成
    log = RawLog(
        user_id=current_user.id,
        content=log_in.content,
        content_type=log_in.content_type,
    )
    session.add(log)
    await session.commit()
    await session.refresh(log)

    # 非同期でContext Analyzerを実行
    # 実際の実装ではCeleryタスクとして実行
    try:
        analysis = await context_analyzer.analyze(log_in.content)
        log.intent = analysis.get("intent")
        log.emotions = analysis.get("emotions")
        log.emotion_scores = analysis.get("emotion_scores")
        log.topics = analysis.get("topics")
        log.is_analyzed = True
        await session.commit()
        await session.refresh(log)
    except Exception:
        # 解析エラーは無視（後でリトライ可能）
        pass

    # 構造分析タスクを非同期でキック
    # Celery タスクとしてバックグラウンドで実行
    try:
        analyze_log_structure.delay(str(log.id))
    except Exception:
        # タスクキューが利用不可でもログ作成は成功させる
        pass

    # 受容的な相槌を返す
    return AckResponse.create_ack(log_id=log.id, intent=log.intent)


@router.get("/", response_model=RawLogListResponse)
async def list_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
):
    """
    ログ一覧を取得（自分のログのみ）
    タイムラインビュー用
    """
    # 総数を取得
    count_result = await session.execute(
        select(func.count(RawLog.id)).where(RawLog.user_id == current_user.id)
    )
    total = count_result.scalar()

    # ページネーション
    offset = (page - 1) * page_size
    result = await session.execute(
        select(RawLog)
        .where(RawLog.user_id == current_user.id)
        .order_by(desc(RawLog.created_at))
        .offset(offset)
        .limit(page_size)
    )
    logs = result.scalars().all()

    return RawLogListResponse(
        items=[RawLogResponse.model_validate(log) for log in logs],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{log_id}", response_model=RawLogResponse)
async def get_log(
    log_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
):
    """特定のログを取得"""
    result = await session.execute(
        select(RawLog).where(
            RawLog.id == log_id,
            RawLog.user_id == current_user.id,
        )
    )
    log = result.scalar_one_or_none()

    if not log:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Log not found",
        )

    return RawLogResponse.model_validate(log)


@router.delete("/{log_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_log(
    log_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
):
    """ログを削除"""
    result = await session.execute(
        select(RawLog).where(
            RawLog.id == log_id,
            RawLog.user_id == current_user.id,
        )
    )
    log = result.scalar_one_or_none()

    if not log:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Log not found",
        )

    await session.delete(log)
    await session.commit()


@router.get("/calendar/{year}/{month}")
async def get_logs_by_month(
    year: int,
    month: int,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
):
    """
    カレンダービュー用: 月別のログ日付リスト
    """
    from datetime import date
    from sqlalchemy import extract

    result = await session.execute(
        select(
            func.date(RawLog.created_at).label("date"),
            func.count(RawLog.id).label("count"),
        )
        .where(
            RawLog.user_id == current_user.id,
            extract("year", RawLog.created_at) == year,
            extract("month", RawLog.created_at) == month,
        )
        .group_by(func.date(RawLog.created_at))
    )
    rows = result.all()

    return {
        "year": year,
        "month": month,
        "entries": [
            {"date": str(row.date), "count": row.count}
            for row in rows
        ],
    }
