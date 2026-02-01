"""
MINDYARD - Celery Tasks
Layer 2 の非同期処理タスク
"""
import asyncio
from typing import Optional
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.workers.celery_app import celery_app
from app.db.base import async_session_maker
from app.models.raw_log import RawLog
from app.models.insight import InsightCard, InsightStatus
from app.services.layer1.context_analyzer import context_analyzer
from app.services.layer2.privacy_sanitizer import privacy_sanitizer
from app.services.layer2.insight_distiller import insight_distiller
from app.services.layer2.sharing_broker import sharing_broker
from app.core.config import settings


def run_async(coro):
    """非同期関数を同期的に実行"""
    loop = asyncio.get_event_loop()
    if loop.is_running():
        # 既存のイベントループがある場合は新しいループを作成
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(asyncio.run, coro)
            return future.result()
    return loop.run_until_complete(coro)


@celery_app.task(bind=True, max_retries=3)
def analyze_log_context(self, log_id: str):
    """
    Layer 1: Context Analyzer タスク
    ログの感情・トピック・インテントを解析
    """
    async def _analyze():
        async with async_session_maker() as session:
            # ログを取得
            result = await session.execute(
                select(RawLog).where(RawLog.id == uuid.UUID(log_id))
            )
            log = result.scalar_one_or_none()

            if not log:
                return {"status": "error", "message": "Log not found"}

            if log.is_analyzed:
                return {"status": "skipped", "message": "Already analyzed"}

            try:
                # 解析実行
                analysis = await context_analyzer.analyze(log.content)

                # 結果を保存
                log.intent = analysis.get("intent")
                log.emotions = analysis.get("emotions")
                log.emotion_scores = analysis.get("emotion_scores")
                log.topics = analysis.get("topics")
                log.is_analyzed = True

                await session.commit()

                return {
                    "status": "success",
                    "log_id": log_id,
                    "intent": str(log.intent) if log.intent else None,
                    "emotions": log.emotions,
                }

            except Exception as e:
                return {"status": "error", "message": str(e)}

    return run_async(_analyze())


@celery_app.task(bind=True, max_retries=3)
def process_log_for_insight(self, log_id: str):
    """
    Layer 2: Gateway Refinery タスク
    ログを匿名化 → 構造化 → 評価 → 保存
    """
    async def _process():
        async with async_session_maker() as session:
            # ログを取得
            result = await session.execute(
                select(RawLog).where(RawLog.id == uuid.UUID(log_id))
            )
            log = result.scalar_one_or_none()

            if not log:
                return {"status": "error", "message": "Log not found"}

            if log.is_processed_for_insight:
                return {"status": "skipped", "message": "Already processed"}

            try:
                # Step 1: Privacy Sanitizer - 匿名化
                sanitized_content, sanitize_metadata = await privacy_sanitizer.sanitize(
                    log.content
                )

                # Step 2: Insight Distiller - 構造化・抽象化
                distilled = await insight_distiller.distill(
                    sanitized_content,
                    metadata={
                        "intent": str(log.intent) if log.intent else None,
                        "emotions": log.emotions,
                        "topics": log.topics,
                    }
                )

                # Step 3: Sharing Broker - 評価
                evaluation = await sharing_broker.evaluate_sharing_value(distilled)

                # Step 4: InsightCard を作成
                insight = InsightCard(
                    author_id=log.user_id,
                    source_log_id=log.id,
                    title=distilled.get("title", ""),
                    context=distilled.get("context"),
                    problem=distilled.get("problem"),
                    solution=distilled.get("solution"),
                    summary=distilled.get("summary", ""),
                    topics=distilled.get("topics"),
                    tags=distilled.get("tags"),
                    sharing_value_score=evaluation.get("sharing_value_score", 0),
                    novelty_score=evaluation.get("novelty_score", 0),
                    generality_score=evaluation.get("generality_score", 0),
                    status=(
                        InsightStatus.PENDING_APPROVAL
                        if evaluation.get("should_propose", False)
                        else InsightStatus.DRAFT
                    ),
                )

                session.add(insight)
                log.is_processed_for_insight = True

                await session.commit()
                await session.refresh(insight)

                return {
                    "status": "success",
                    "log_id": log_id,
                    "insight_id": str(insight.id),
                    "should_propose": evaluation.get("should_propose", False),
                    "sharing_value_score": evaluation.get("sharing_value_score", 0),
                }

            except Exception as e:
                return {"status": "error", "message": str(e)}

    return run_async(_process())


@celery_app.task
def process_all_unprocessed_logs():
    """
    未処理のログをすべて処理するバッチタスク
    """
    async def _process_all():
        async with async_session_maker() as session:
            # 未処理のログを取得
            result = await session.execute(
                select(RawLog).where(
                    RawLog.is_analyzed == True,
                    RawLog.is_processed_for_insight == False,
                ).limit(100)  # バッチサイズ
            )
            logs = result.scalars().all()

            processed = []
            for log in logs:
                # 個別タスクをキューに追加
                process_log_for_insight.delay(str(log.id))
                processed.append(str(log.id))

            return {
                "status": "success",
                "queued_count": len(processed),
                "log_ids": processed,
            }

    return run_async(_process_all())
