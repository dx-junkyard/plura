"""
MINDYARD - Log Endpoints
Layer 1: Private Logger API
"""
from datetime import datetime
from typing import Optional
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status, UploadFile, File
from fastapi.responses import JSONResponse
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from openai import AsyncOpenAI

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
from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()

# OpenAI クライアント（Whisper用）
_openai_client = None

def get_openai_client() -> AsyncOpenAI:
    """OpenAI クライアントのシングルトン取得"""
    global _openai_client
    if _openai_client is None and settings.openai_api_key:
        _openai_client = AsyncOpenAI(api_key=settings.openai_api_key)
    return _openai_client


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
        logger.info(f"[POST /logs/] Celery task queued for log_id={log.id}")
    except Exception as e:
        # タスクキューが利用不可でもログ作成は成功させる
        logger.warning(f"[POST /logs/] Failed to queue Celery task: {e}")

    logger.info(
        f"[POST /logs/] Returning AckResponse: log_id={log.id}, "
        f"is_analyzed={log.is_analyzed}, intent={log.intent}"
    )

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
    logger.info(f"[GET /logs/{log_id}] Request received from user={current_user.id}")
    result = await session.execute(
        select(RawLog).where(
            RawLog.id == log_id,
            RawLog.user_id == current_user.id,
        )
    )
    log = result.scalar_one_or_none()

    if not log:
        logger.warning(f"[GET /logs/{log_id}] Log not found for user={current_user.id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Log not found",
        )

    logger.info(
        f"[GET /logs/{log_id}] DB state: "
        f"is_analyzed={log.is_analyzed}, "
        f"is_structure_analyzed={log.is_structure_analyzed}, "
        f"intent={log.intent}, "
        f"has_structural_analysis={log.structural_analysis is not None}, "
        f"has_probing_question={bool(log.structural_analysis and log.structural_analysis.get('probing_question'))}"
    )

    try:
        response_data = RawLogResponse.model_validate(log)
        logger.info(
            f"[GET /logs/{log_id}] Response serialized OK: "
            f"is_analyzed={response_data.is_analyzed}, "
            f"is_structure_analyzed={response_data.is_structure_analyzed}"
        )
        # Cache-Control: ポーリングでブラウザキャッシュが使われないようにする
        return JSONResponse(
            content=response_data.model_dump(mode="json"),
            headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"},
        )
    except Exception as e:
        logger.error(f"[GET /logs/{log_id}] Serialization error: {type(e).__name__}: {e}")
        raise


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


@router.post("/transcribe", response_model=AckResponse, status_code=status.HTTP_201_CREATED)
async def transcribe_audio(
    audio: UploadFile = File(...),
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
):
    """
    音声ファイルをWhisper APIで文字起こしし、ログとして保存

    - 音声ファイルを受け取り、OpenAI Whisper APIで文字起こし
    - 文字起こし結果をログとして保存
    - Context Analyzer と Structural Analyzer を実行
    """
    client = get_openai_client()

    if not client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="音声認識サービスが利用できません。API キーを確認してください。",
        )

    # 音声ファイルの検証
    allowed_types = [
        "audio/webm", "audio/mp4", "audio/mpeg", "audio/mpga",
        "audio/m4a", "audio/wav", "audio/ogg", "audio/flac"
    ]
    if audio.content_type and audio.content_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"サポートされていない音声形式です: {audio.content_type}",
        )

    try:
        # 音声ファイルを読み取り
        audio_content = await audio.read()

        # Whisper API で文字起こし
        transcription = await client.audio.transcriptions.create(
            model="whisper-1",
            file=(audio.filename or "audio.webm", audio_content, audio.content_type or "audio/webm"),
            language="ja",  # 日本語を指定
        )

        transcribed_text = transcription.text.strip()

        if not transcribed_text:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="音声を認識できませんでした。もう一度お試しください。",
            )

        # ログの作成
        log = RawLog(
            user_id=current_user.id,
            content=transcribed_text,
            content_type="voice",  # 音声入力であることを記録
        )
        session.add(log)
        await session.commit()
        await session.refresh(log)

        # Context Analyzer を実行
        try:
            analysis = await context_analyzer.analyze(transcribed_text)
            log.intent = analysis.get("intent")
            log.emotions = analysis.get("emotions")
            log.emotion_scores = analysis.get("emotion_scores")
            log.topics = analysis.get("topics")
            log.is_analyzed = True
            await session.commit()
            await session.refresh(log)
        except Exception:
            # 解析エラーは無視
            pass

        # 構造分析タスクを非同期でキック
        try:
            analyze_log_structure.delay(str(log.id))
        except Exception:
            # タスクキューが利用不可でもログ作成は成功させる
            pass

        # 受容的な相槌を返す（音声入力の場合は文字起こしテキストも含める）
        return AckResponse.create_ack(
            log_id=log.id,
            intent=log.intent,
            transcribed_text=transcribed_text,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"音声の処理中にエラーが発生しました: {str(e)}",
        )
