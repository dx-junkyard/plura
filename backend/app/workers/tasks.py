"""
MINDYARD - Celery Tasks
Layer 2 の非同期処理タスク
"""
import asyncio
import logging
from typing import Optional
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.workers.celery_app import celery_app
from app.db.base import async_session_maker, engine
from app.models.raw_log import RawLog
from app.models.insight import InsightCard, InsightStatus
from app.services.layer1.context_analyzer import context_analyzer
from app.services.layer2.privacy_sanitizer import privacy_sanitizer
from app.services.layer2.insight_distiller import insight_distiller
from app.services.layer2.sharing_broker import sharing_broker
from app.services.layer2.structural_analyzer import structural_analyzer
from app.core.config import settings

logger = logging.getLogger(__name__)


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
        # Ensure engine connection pool is clean for this process/task
        # This prevents issues with inherited connections in forked processes
        await engine.dispose()

        async with async_session_maker() as session:
            # ログを取得
            result = await session.execute(
                select(RawLog).where(RawLog.id == uuid.UUID(log_id))
            )
            log = result.scalar_one_or_none()

            if not log:
                logger.error(f"Log not found for context analysis: {log_id}")
                return {"status": "error", "message": "Log not found"}

            if log.is_analyzed:
                logger.info(f"Log already analyzed for context: {log_id}")
                return {"status": "skipped", "message": "Already analyzed"}

            try:
                logger.info(f"Starting context analysis for log_id: {log_id}")
                # 解析実行
                analysis = await context_analyzer.analyze(log.content)

                # 結果を保存
                log.intent = analysis.get("intent")
                log.emotions = analysis.get("emotions")
                log.emotion_scores = analysis.get("emotion_scores")
                log.topics = analysis.get("topics")
                log.is_analyzed = True

                # Mark JSON/Array fields as modified to ensure SQLAlchemy detects changes
                flag_modified(log, "emotion_scores")

                logger.info(f"Committing context analysis for log_id: {log_id}")
                await session.commit()
                logger.info(f"Successfully committed context analysis for log_id: {log_id}")

                return {
                    "status": "success",
                    "log_id": log_id,
                    "intent": str(log.intent) if log.intent else None,
                    "emotions": log.emotions,
                }

            except Exception as e:
                logger.error(f"Error in analyze_log_context for {log_id}: {str(e)}", exc_info=True)
                return {"status": "error", "message": str(e)}

    return run_async(_analyze())


@celery_app.task(bind=True, max_retries=3)
def analyze_log_structure(self, log_id: str):
    """
    Layer 2: Structural Analyzer タスク
    文脈依存型・構造的理解アップデート

    過去の会話履歴と直前の構造的理解を踏まえ、
    新しいログの関係性を判定し構造的課題を更新する。
    """
    async def _analyze_structure():
        # Ensure engine connection pool is clean for this process/task
        await engine.dispose()

        async with async_session_maker() as session:
            # 現在のログを取得
            result = await session.execute(
                select(RawLog).where(RawLog.id == uuid.UUID(log_id))
            )
            log = result.scalar_one_or_none()

            if not log:
                logger.error(f"Log not found for structural analysis: {log_id}")
                return {"status": "error", "message": "Log not found"}

            if log.is_structure_analyzed:
                logger.info(f"Log already analyzed for structure: {log_id}")
                return {"status": "skipped", "message": "Already analyzed for structure"}

            try:
                logger.info(f"Starting structural analysis for log_id: {log_id}")
                # --- Topic overlap filter to avoid irrelevant history ---
                def _normalize(text: str):
                    tokens = re.split(r"[^\\wぁ-んァ-ン一-龥]+", text.lower())
                    stop = {"の", "に", "と", "で", "が", "は", "を", "も", "へ", "and", "or", "the", "a", "an"}
                    return [t for t in tokens if len(t) > 1 and t not in stop]

                current_tokens = set(_normalize(log.content))

                # Step 1: 履歴取得 - 同じユーザーの直近5件のログを取得（今回のログを除く）
                history_result = await session.execute(
                    select(RawLog)
                    .where(
                        RawLog.user_id == log.user_id,
                        RawLog.id != log.id,
                    )
                    .order_by(RawLog.created_at.desc())
                    .limit(5)
                )
                candidates = history_result.scalars().all()

                past_logs = []
                for prev in candidates:
                    overlap = current_tokens & set(_normalize(prev.content))
                    if overlap:
                        past_logs.append(prev)
                    else:
                        logger.info(f"[structural] skip history log {prev.id} (no topical overlap)")

                # Step 2: 前回仮説の抽出
                previous_hypothesis = None
                if past_logs:
                    latest_prev_log = past_logs[0]
                    if latest_prev_log.structural_analysis:
                        # updated_structural_issue を優先、なければ structural_issue
                        previous_hypothesis = (
                            latest_prev_log.structural_analysis.get("updated_structural_issue")
                            or latest_prev_log.structural_analysis.get("structural_issue")
                        )

                # Step 3: 要約リスト作成
                recent_history = []
                for prev_log in past_logs:
                    # コンテンツを短く切り詰める（100文字まで）
                    summary = prev_log.content[:100]
                    if len(prev_log.content) > 100:
                        summary += "..."
                    recent_history.append(summary)

                # Step 4: StructuralAnalyzer 実行
                analysis = await structural_analyzer.analyze(
                    current_log=log.content,
                    recent_history=recent_history if recent_history else None,
                    previous_hypothesis=previous_hypothesis,
                )

                # 結果を保存
                log.structural_analysis = analysis
                # Explicitly set the completion flag
                log.is_structure_analyzed = True

                # Mark JSON fields as modified to ensure SQLAlchemy detects changes
                flag_modified(log, "structural_analysis")

                logger.info(f"Committing structural analysis for log_id: {log_id}")
                await session.commit()
                logger.info(f"Successfully committed structural analysis for log_id: {log_id}")

                return {
                    "status": "success",
                    "log_id": log_id,
                    "relationship_type": analysis.get("relationship_type"),
                    "updated_structural_issue": analysis.get("updated_structural_issue"),
                    "probing_question": analysis.get("probing_question"),
                }

            except Exception as e:
                logger.error(f"Error in analyze_log_structure for {log_id}: {str(e)}", exc_info=True)
                return {"status": "error", "message": str(e)}

    return run_async(_analyze_structure())


@celery_app.task(bind=True, max_retries=3)
def process_log_for_insight(self, log_id: str):
    """
    Layer 2: Gateway Refinery タスク
    ログを匿名化 → 構造化 → 評価 → 保存
    """
    async def _process():
        # Ensure engine connection pool is clean for this process/task
        await engine.dispose()

        async with async_session_maker() as session:
            # ログを取得
            result = await session.execute(
                select(RawLog).where(RawLog.id == uuid.UUID(log_id))
            )
            log = result.scalar_one_or_none()

            if not log:
                logger.error(f"Log not found for insight processing: {log_id}")
                return {"status": "error", "message": "Log not found"}

            if log.is_processed_for_insight:
                logger.info(f"Log already processed for insight: {log_id}")
                return {"status": "skipped", "message": "Already processed"}

            try:
                logger.info(f"Starting insight processing for log_id: {log_id}")
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

                logger.info(f"Committing insight processing for log_id: {log_id}")
                await session.commit()
                logger.info(f"Successfully committed insight processing for log_id: {log_id}")

                await session.refresh(insight)

                return {
                    "status": "success",
                    "log_id": log_id,
                    "insight_id": str(insight.id),
                    "should_propose": evaluation.get("should_propose", False),
                    "sharing_value_score": evaluation.get("sharing_value_score", 0),
                }

            except Exception as e:
                logger.error(f"Error in process_log_for_insight for {log_id}: {str(e)}", exc_info=True)
                return {"status": "error", "message": str(e)}

    return run_async(_process())


@celery_app.task
def process_all_unprocessed_logs():
    """
    未処理のログをすべて処理するバッチタスク
    """
    async def _process_all():
        # Ensure engine connection pool is clean for this process/task
        await engine.dispose()

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
