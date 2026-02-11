"""
MINDYARD - Celery Tasks
Layer 2 の非同期処理タスク
"""
import asyncio
import logging
from typing import Optional
import uuid
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.workers.celery_app import celery_app
from app.db.base import async_session_maker, engine
from app.models.raw_log import RawLog, LogIntent
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
                log.tags = analysis.get("tags")
                log.metadata_analysis = analysis.get("metadata_analysis")
                log.is_analyzed = True

                # Mark JSON/Array fields as modified to ensure SQLAlchemy detects changes
                flag_modified(log, "emotion_scores")
                flag_modified(log, "metadata_analysis")

                logger.info(f"Committing context analysis for log_id: {log_id}")
                await session.commit()
                logger.info(f"Successfully committed context analysis for log_id: {log_id}")

                return {
                    "status": "success",
                    "log_id": log_id,
                    "intent": str(log.intent) if log.intent else None,
                    "emotions": log.emotions,
                    "tags": log.tags,
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

            # 状態ログは構造分析をスキップし、マイクロフィードバックを返す
            if log.intent == LogIntent.STATE or log.intent == "state":
                logger.info(f"Generating micro-feedback for state log: {log_id}")
                try:
                    analysis = await structural_analyzer.generate_state_feedback(
                        content=log.content,
                        emotions=log.emotions,
                    )
                    log.structural_analysis = analysis
                    log.is_structure_analyzed = True
                    flag_modified(log, "structural_analysis")
                    await session.commit()
                    logger.info(f"State micro-feedback saved for log_id: {log_id}")
                    return {
                        "status": "success",
                        "log_id": log_id,
                        "relationship_type": analysis.get("relationship_type"),
                        "probing_question": analysis.get("probing_question"),
                    }
                except Exception as e:
                    logger.error(f"Error generating state feedback for {log_id}: {str(e)}", exc_info=True)
                    return {"status": "error", "message": str(e)}

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

                # Step 4: 感情スコアの最大値を取得
                max_emotion_score = 0.0
                if log.emotion_scores and isinstance(log.emotion_scores, dict):
                    scores = log.emotion_scores.values()
                    max_emotion_score = max(scores) if scores else 0.0

                # Step 5: StructuralAnalyzer 実行
                analysis = await structural_analyzer.analyze(
                    current_log=log.content,
                    recent_history=recent_history if recent_history else None,
                    previous_hypothesis=previous_hypothesis,
                    max_emotion_score=max_emotion_score,
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
                        "tags": log.tags,
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


@celery_app.task(bind=True, max_retries=3)
def deep_research_task(self, query: str, user_id: str):
    """
    対話型ディープ・リサーチ・タスク

    knowledge_node / research_trigger_node からキックされる非同期調査タスク。
    DEEPモデルで詳細な調査を行い、InsightDistillerで構造化し、
    データベースを更新してWebSocket（将来）でフロントエンドへ通知する。

    処理フロー:
    1. DEEPモデルで包括的な調査レポートを生成
    2. InsightDistillerで結果を構造化
    3. データベース（RawLog）に調査結果を保存
    4. WebSocket通知（現在はログ出力で代替、将来対応予定）
    """
    async def _research():
        await engine.dispose()

        try:
            logger.info(
                f"Starting deep research for user_id: {user_id}, query: {query[:100]}"
            )

            from app.core.llm import llm_manager
            from app.core.llm_provider import LLMUsageRole

            provider = llm_manager.get_client(LLMUsageRole.DEEP)
            await provider.initialize()

            system_prompt = """あなたは詳細な調査・リサーチを行うアシスタントです。
以下の質問について、深く掘り下げた包括的な調査レポートを作成してください。

レポートのフォーマット:
1. 概要: 質問への総合的な回答
2. 詳細分析: 各論点の掘り下げ
3. エビデンス: 根拠となる情報・データ
4. 結論と推奨: まとめと次のアクション

日本語で応答してください。"""

            result = await provider.generate_text(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": query},
                ],
                temperature=0.3,
            )

            raw_report = result.content
            logger.info(f"Deep research LLM completed for user_id: {user_id}")

            # InsightDistiller で結果を構造化
            structured_result = None
            try:
                structured_result = await insight_distiller.distill(
                    raw_report,
                    metadata={
                        "intent": "deep_research",
                        "emotions": [],
                        "topics": [],
                        "tags": ["deep_research"],
                    },
                )
                logger.info(
                    f"Deep research structured for user_id: {user_id}, "
                    f"title: {structured_result.get('title', 'N/A')}"
                )
            except Exception as e:
                logger.warning(
                    f"InsightDistiller failed for deep research: {str(e)}",
                    exc_info=True,
                )

            # データベースに調査結果をRawLogとして保存
            saved_log_id = None
            try:
                async with async_session_maker() as session:
                    research_log = RawLog(
                        user_id=uuid.UUID(user_id) if user_id else None,
                        content=f"[Deep Research] {query}\n\n{raw_report}",
                        content_type="text",
                        intent=LogIntent.LOG,
                        topics=structured_result.get("topics", []) if structured_result else [],
                        tags=(structured_result.get("tags", []) if structured_result else []) + ["deep_research"],
                        is_analyzed=True,
                    )
                    session.add(research_log)
                    await session.commit()
                    await session.refresh(research_log)
                    saved_log_id = str(research_log.id)
                    logger.info(f"Deep research saved as RawLog: {saved_log_id}")
            except Exception as e:
                logger.warning(
                    f"Failed to save deep research to DB: {str(e)}",
                    exc_info=True,
                )

            # WebSocket通知（将来対応予定）
            # 現在はログ出力で代替。WebSocket実装後に以下を置き換える:
            # await websocket_manager.send_to_user(user_id, {
            #     "type": "deep_research_completed",
            #     "query": query,
            #     "report_preview": raw_report[:200],
            #     "log_id": saved_log_id,
            # })
            logger.info(
                f"[WebSocket placeholder] Deep research completed notification "
                f"for user_id: {user_id}, log_id: {saved_log_id}"
            )

            return {
                "status": "success",
                "user_id": user_id,
                "query": query,
                "report": raw_report,
                "structured": structured_result,
                "log_id": saved_log_id,
            }

        except Exception as e:
            logger.error(
                f"Error in deep_research_task for user_id {user_id}: {str(e)}",
                exc_info=True,
            )
            return {"status": "error", "message": str(e)}

    return run_async(_research())


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
