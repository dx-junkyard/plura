"""
MINDYARD - Celery Tasks
Layer 2 の非同期処理タスク
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple
import uuid
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.workers.celery_app import celery_app
from app.db.base import async_session_maker, engine
from app.models.raw_log import RawLog, LogIntent
from app.models.insight import InsightCard, InsightStatus
from app.models.user import User
from app.services.layer1.context_analyzer import context_analyzer
from app.services.layer2.privacy_sanitizer import privacy_sanitizer
from app.services.layer2.insight_distiller import insight_distiller
from app.services.layer2.sharing_broker import sharing_broker
from app.services.layer2.structural_analyzer import structural_analyzer, is_continuation_phrase
from app.services.layer3.knowledge_store import knowledge_store
from app.core.security import get_password_hash
from app.core.config import settings

logger = logging.getLogger(__name__)

DEFAULT_SYSTEM_BOT_USER_ID = "00000000-0000-0000-0000-000000000001"


def _split_research_report(report: str) -> Tuple[str, str]:
    """
    Deep Research レポートを summary / details に分離する。
    """
    text = (report or "").strip()
    if not text:
        return ("調査結果を取得できませんでした。", "")

    # 「概要」セクションを優先的に抽出
    heading_pattern = re.compile(r"(?:^|\n)#{0,3}\s*概要[：:\s]*\n?", re.IGNORECASE)
    heading_match = heading_pattern.search(text)
    if heading_match:
        start = heading_match.end()
        remainder = text[start:]
        next_heading = re.search(r"\n#{1,6}\s+|\n(?:主要|詳細|結論|次のステップ)", remainder)
        summary = (remainder[:next_heading.start()] if next_heading else remainder).strip()
        if summary:
            return (summary[:500], text)

    # フォールバック: 冒頭段落を summary とする
    first_paragraph = re.split(r"\n\s*\n", text, maxsplit=1)[0].strip()
    summary = first_paragraph[:500] if first_paragraph else text[:500]
    return (summary, text)


def _build_research_assistant_reply(summary: str, is_cache_hit: bool) -> str:
    source_note = "（既存ナレッジを再利用）" if is_cache_hit else "（新規に調査実行）"
    return f"🔬 **Deep Research 結果 {source_note}**\n\n{summary}"


async def _ensure_system_bot_user(session: AsyncSession) -> uuid.UUID:
    """
    Deep Research 共有財産の所有者となる system bot ユーザーを保証する。
    """
    configured = getattr(settings, "system_bot_user_id", None) or DEFAULT_SYSTEM_BOT_USER_ID
    system_user_id = uuid.UUID(configured)

    existing = await session.get(User, system_user_id)
    if existing:
        return system_user_id

    email_result = await session.execute(
        select(User).where(User.email == "system-bot@mindyard.local")
    )
    existing_by_email = email_result.scalar_one_or_none()
    if existing_by_email:
        return existing_by_email.id

    system_user = User(
        id=system_user_id,
        email="system-bot@mindyard.local",
        hashed_password=get_password_hash(str(uuid.uuid4())),
        display_name="MINDYARD System",
        is_active=True,
        is_verified=True,
    )
    session.add(system_user)
    await session.flush()
    return system_user_id


async def _find_cached_research_insight(cache_query: str) -> Optional[InsightCard]:
    """
    既存の Deep Research Insight をベクトル検索で探索する。
    """
    similar = await knowledge_store.search_similar(
        query=cache_query,
        limit=1,
        score_threshold=0.88,
        filter_tags=["deep_research"],
    )
    if not similar:
        return None

    best = similar[0]
    insight_id = best.get("insight_id")
    if not insight_id:
        return None

    try:
        target_id = uuid.UUID(str(insight_id))
    except Exception:
        return None

    async with async_session_maker() as session:
        result = await session.execute(
            select(InsightCard).where(
                InsightCard.id == target_id,
                InsightCard.status == InsightStatus.APPROVED,
            )
        )
        return result.scalar_one_or_none()


def _build_cached_report(insight: InsightCard) -> Tuple[str, str]:
    summary = (insight.summary or "").strip() or "既存の調査結果を再利用しました。"
    parts = [
        f"## {insight.title}",
        "",
        summary,
    ]
    if insight.context:
        parts.extend(["", "### 背景", insight.context])
    if insight.problem:
        parts.extend(["", "### 課題", insight.problem])
    if insight.solution:
        parts.extend(["", "### 知見", insight.solution])
    return (summary[:500], "\n".join(parts).strip())


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
                # 「続きから」「続きで」等のときはトークン重なりで履歴を捨てない（直前ログを必ず使う）
                use_overlap_filter = not is_continuation_phrase(log.content or "")

                # Step 1: 履歴取得 - 同一スレッドがあればそのスレッド内の直近5件、なければ従来どおりユーザー直近5件
                history_query = select(RawLog).where(
                    RawLog.user_id == log.user_id,
                    RawLog.id != log.id,
                ).order_by(RawLog.created_at.desc()).limit(5)
                if getattr(log, "thread_id", None) is not None:
                    history_query = history_query.where(RawLog.thread_id == log.thread_id)
                history_result = await session.execute(history_query)
                candidates = history_result.scalars().all()

                past_logs = []
                for prev in candidates:
                    if use_overlap_filter:
                        overlap = current_tokens & set(_normalize(prev.content))
                        if overlap:
                            past_logs.append(prev)
                        else:
                            logger.info(f"[structural] skip history log {prev.id} (no topical overlap)")
                    else:
                        past_logs.append(prev)

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


# ════════════════════════════════════════
# 品質ゲート: Insight化する価値があるかの事前チェック
# ════════════════════════════════════════
_MIN_CONTENT_LENGTH = 30  # これ未満はInsight化しない
_TRIVIAL_PATTERNS = {
    "おはよう", "おやすみ", "ありがとう", "了解", "OK", "ok", "はい",
    "テスト", "test", "あ", "うん", "そう", "なるほど",
}


def _check_insight_eligibility(log: RawLog) -> Optional[str]:
    """
    ログがInsight化に値するかチェックする。
    不適格なら理由文字列を返す。適格なら None を返す。
    """
    content = (log.content or "").strip()

    # 1. 短すぎるログ
    if len(content) < _MIN_CONTENT_LENGTH:
        return f"too_short ({len(content)} < {_MIN_CONTENT_LENGTH})"

    # 2. STATE（状態記録）は知恵にならない
    if log.intent and log.intent.value == "state":
        return "intent_is_state"

    # 3. 定型的・意味のない投稿
    normalized = content.replace("。", "").replace("！", "").replace("？", "").strip()
    if normalized in _TRIVIAL_PATTERNS:
        return f"trivial_content: {normalized}"

    # 4. 数字だけ・記号だけ
    if re.fullmatch(r"[\d\s\W]+", content):
        return "numeric_or_symbols_only"

    return None


@celery_app.task(bind=True, max_retries=3)
def process_log_for_insight(self, log_id: str):
    """
    Layer 2: Gateway Refinery タスク
    品質ゲート → 匿名化 → 構造化 → 評価 → 保存
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

            # ── 品質ゲート: Insight化する価値があるかを事前チェック ──
            skip_reason = _check_insight_eligibility(log)
            if skip_reason:
                log.is_processed_for_insight = True
                await session.commit()
                logger.info(
                    f"Insight skipped (quality gate): log_id={log_id}, reason={skip_reason}"
                )
                return {"status": "skipped", "message": skip_reason}

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

                # Step 2.5: Distiller が「知恵にならない」と判断した場合はスキップ
                if distilled.get("not_suitable"):
                    log.is_processed_for_insight = True
                    await session.commit()
                    logger.info(
                        f"Insight skipped (distiller: not_suitable): log_id={log_id}"
                    )
                    return {"status": "skipped", "message": "not_suitable_for_wisdom"}

                # Step 3: Sharing Broker - 評価
                evaluation = await sharing_broker.evaluate_sharing_value(distilled)

                sharing_score = evaluation.get("sharing_value_score", 0)
                should_propose = evaluation.get("should_propose", False)
                novelty_score = evaluation.get("novelty_score", 0)
                generality_score = evaluation.get("generality_score", 0)
                reasoning = (evaluation.get("reasoning") or "").strip()

                # 評価の思考プロセスを可視化（チューニング用）
                logger.info(
                    "Insight evaluation: log_id=%s, sharing_value_score=%.1f, "
                    "should_propose=%s, novelty_score=%.1f, generality_score=%.1f, "
                    "reasoning=%s",
                    log_id,
                    float(sharing_score),
                    should_propose,
                    float(novelty_score),
                    float(generality_score),
                    reasoning or "(empty)",
                )

                # Step 4: ステータス判定
                #   score >= 80 → 推奨（ユーザーに共有を提案）
                #   score <  80 → 通常（保存のみ）
                #   ※ 公開はユーザーの承認が必須。自動公開は行わない。
                if should_propose:
                    insight_status = InsightStatus.PENDING_APPROVAL
                else:
                    insight_status = InsightStatus.DRAFT

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
                    sharing_value_score=sharing_score,
                    novelty_score=novelty_score,
                    generality_score=generality_score,
                    status=insight_status,
                )

                session.add(insight)
                log.is_processed_for_insight = True

                logger.info(f"Committing insight processing for log_id: {log_id}")
                await session.commit()
                logger.info(f"Successfully committed insight processing for log_id: {log_id}")

                await session.refresh(insight)

                promotion_type = "推奨" if should_propose else "通常"
                logger.info(
                    f"Insight pipeline complete: log_id={log_id}, "
                    f"insight_id={insight.id}, score={sharing_score}, "
                    f"type={promotion_type}, should_propose={should_propose}, "
                    f"reasoning={reasoning or '(empty)'}"
                )

                return {
                    "status": "success",
                    "log_id": log_id,
                    "insight_id": str(insight.id),
                    "should_propose": should_propose,
                    "sharing_value_score": sharing_score,
                    "promotion_type": promotion_type,
                }

            except Exception as e:
                logger.error(f"Error in process_log_for_insight for {log_id}: {str(e)}", exc_info=True)
                return {"status": "error", "message": str(e)}

    return run_async(_process())


@celery_app.task(bind=True, max_retries=3)
def deep_research_task(self, query: str, user_id: str):
    """
    Knowledge Node からキックされる非同期調査タスク

    ユーザーの質問に対してDEEPモデルで詳細な調査を行い、
    結果をCeleryバックエンド経由で返す。
    将来的にWebSocket通知やDB保存にも対応可能。
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

            logger.info(f"Deep research completed for user_id: {user_id}")

            return {
                "status": "success",
                "user_id": user_id,
                "query": query,
                "report": result.content,
            }

        except Exception as e:
            logger.error(
                f"Error in deep_research_task for user_id {user_id}: {str(e)}",
                exc_info=True,
            )
            return {"status": "error", "message": str(e)}

    return run_async(_research())


@celery_app.task(bind=True, max_retries=3)
def run_deep_research_task(
    self,
    user_id: str,
    thread_id: str,
    query: str,
    initial_context: str,
    research_log_id: str,
    research_plan: Optional[Dict[str, Any]] = None,
):
    """
    Deep Research 非同期タスク

    deep_research_node からキックされ、DEEP モデルで詳細調査を行い、
    結果を RawLog の assistant_reply に保存する。

    Args:
        user_id: ユーザーID
        thread_id: 会話スレッドID
        query: 調査クエリ（ユーザーの元の質問）
        initial_context: 初回回答（深掘り用コンテキスト）
        research_log_id: 結果を保存する RawLog の ID（事前生成）
    """
    async def _research():
        await engine.dispose()

        try:
            logger.info(
                f"Starting deep research task for user_id: {user_id}, "
                f"log_id: {research_log_id}, query: {query[:100]}"
            )

            from app.core.llm import llm_manager
            from app.core.llm_provider import LLMUsageRole

            plan = research_plan if isinstance(research_plan, dict) else {}
            cache_query_parts = [
                query,
                plan.get("topic", ""),
                plan.get("scope", ""),
                " ".join(plan.get("perspectives", [])) if isinstance(plan.get("perspectives"), list) else "",
            ]
            cache_query = "\n".join([p for p in cache_query_parts if p]).strip()

            cached_insight = await _find_cached_research_insight(cache_query or query)
            cached_insight_id = None
            is_cache_hit = cached_insight is not None

            if cached_insight:
                cached_insight_id = str(cached_insight.id)
                summary_text, detailed_report = _build_cached_report(cached_insight)
                logger.info(
                    "Deep research cache hit",
                    extra={"research_log_id": research_log_id, "insight_id": cached_insight_id},
                )
            else:
                provider = llm_manager.get_client(LLMUsageRole.DEEP)
                await provider.initialize()

                system_prompt = (
                    "あなたはMINDYARDの Deep Research アシスタントです。\n"
                    "ユーザーのクエリに対して、徹底的かつ包括的な調査レポートを作成してください。\n\n"
                    "### 出力制約（厳守）:\n"
                    "- **文字数: 2,000〜3,000文字**に収めること。超過禁止。\n"
                    "- 詳細は**箇条書き（・ や - ）**で簡潔にまとめる。\n"
                    "- Markdownテーブルを使う場合、**各セルは50文字以内**にすること。\n"
                    "- 冗長な前置き・繰り返しを避け、情報密度を高く保つ。\n\n"
                    "### 調査方針:\n"
                    "1. **多角的な視点**: 複数の観点からトピックを分析する\n"
                    "2. **構造化された回答**: 見出し・箇条書きを使って情報を整理する\n"
                    "3. **エビデンスベース**: 主張には根拠や出典の方向性を示す\n"
                    "4. **実用性重視**: ユーザーが次のアクションを取れる具体的情報\n\n"
                    "### 出力フォーマット:\n"
                    "- 概要（1-2文のサマリー）\n"
                    "- 主要な発見・知見（箇条書き）\n"
                    "- 詳細分析（各ポイントの掘り下げ）\n"
                    "- 次のステップの提案\n\n"
                    "### 注意事項:\n"
                    "- 日本語で応答する\n"
                    "- 確証のない情報は「〜の可能性があります」等と明記する\n"
                    "- 専門用語には簡潔な説明を付ける\n"
                )

                research_query = query
                if initial_context:
                    research_query = (
                        f"元の質問: {query}\n\n"
                        f"初回の回答（これを深掘りしてください）:\n{initial_context}"
                    )

                if plan:
                    plan_lines = [
                        f"- タイトル: {plan.get('title', '')}",
                        f"- 調査主題: {plan.get('topic', '')}",
                        f"- 調査範囲: {plan.get('scope', '')}",
                        "- 視点: " + (
                            ", ".join(plan.get("perspectives", []))
                            if isinstance(plan.get("perspectives"), list)
                            else str(plan.get("perspectives", ""))
                        ),
                    ]
                    research_query += "\n\n調査計画書（ユーザー承認済み）:\n" + "\n".join(plan_lines)

                result = await provider.generate_text(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": research_query},
                    ],
                    temperature=0.3,
                )

                research_report = result.content
                summary_text, detailed_report = _split_research_report(research_report)
                logger.info(
                    f"Deep research completed for log_id: {research_log_id}, "
                    f"length: {len(research_report)}"
                )

            assistant_reply = _build_research_assistant_reply(summary_text, is_cache_hit=is_cache_hit)
            logger.info(
                f"Deep research result prepared for log_id: {research_log_id}, "
                f"cache_hit: {is_cache_hit}"
            )

            # 結果を RawLog に保存
            # Path 1 (POST /logs/): 既存ログを更新
            # Path 2 (conversation graph): 新規ログを作成（system 所有）
            async with async_session_maker() as session:
                system_bot_user_id = await _ensure_system_bot_user(session)
                metadata_analysis = {
                    "deep_research": {
                        "title": plan.get("title") if isinstance(plan, dict) else None,
                        "topic": plan.get("topic") if isinstance(plan, dict) else None,
                        "scope": plan.get("scope") if isinstance(plan, dict) else None,
                        "perspectives": plan.get("perspectives", []) if isinstance(plan, dict) else [],
                        "summary": summary_text,
                        "details": detailed_report,
                        "requested_by_user_id": user_id,
                        "is_cache_hit": is_cache_hit,
                        "cached_insight_id": cached_insight_id,
                    }
                }
                existing_log = await session.get(RawLog, uuid.UUID(research_log_id))
                if existing_log:
                    # 既存ログを更新（POST /logs/ で作成済みのログ）
                    existing_log.assistant_reply = assistant_reply
                    existing_log.metadata_analysis = metadata_analysis
                    existing_log.is_analyzed = True
                    existing_log.is_structure_analyzed = True
                    existing_log.is_processed_for_insight = True
                    log = existing_log
                else:
                    # 新規ログを作成（conversation graph 経由）
                    log = RawLog(
                        id=uuid.UUID(research_log_id),
                        user_id=system_bot_user_id,
                        thread_id=uuid.UUID(thread_id) if thread_id else None,
                        content=query,
                        content_type="deep_research",
                        assistant_reply=assistant_reply,
                        metadata_analysis=metadata_analysis,
                        is_analyzed=True,
                        is_structure_analyzed=True,
                        is_processed_for_insight=True,
                    )
                    session.add(log)
                await session.flush()

                # Deep Research は即時に共有財産（APPROVED Insight）として作成
                if not is_cache_hit:
                    topic = plan.get("topic") if isinstance(plan, dict) else None
                    insight = InsightCard(
                        author_id=system_bot_user_id,
                        source_log_id=log.id,
                        title=(plan.get("title") if isinstance(plan, dict) else None) or query[:120],
                        context=(plan.get("scope") if isinstance(plan, dict) else None),
                        problem=topic,
                        solution=detailed_report[:4000],
                        summary=summary_text,
                        topics=[topic] if topic else None,
                        tags=["deep_research", "shared_asset"],
                        sharing_value_score=100.0,
                        novelty_score=0.0,
                        generality_score=100.0,
                        status=InsightStatus.APPROVED,
                        published_at=datetime.now(timezone.utc),
                    )
                    session.add(insight)
                    await session.flush()

                    vector_id = await knowledge_store.store_insight(
                        insight_id=str(insight.id),
                        insight={
                            "title": insight.title,
                            "context": insight.context,
                            "problem": insight.problem,
                            "solution": insight.solution,
                            "summary": insight.summary,
                            "topics": insight.topics or [],
                            "tags": insight.tags or [],
                        },
                    )
                    if vector_id:
                        insight.vector_id = vector_id

                await session.commit()
                logger.info(f"Deep research result saved to log_id: {research_log_id}")

            return {
                "status": "success",
                "log_id": research_log_id,
                "user_id": user_id,
                "report_length": len(detailed_report),
                "cache_hit": is_cache_hit,
            }

        except Exception as e:
            logger.error(
                f"Error in run_deep_research_task for log_id {research_log_id}: {str(e)}",
                exc_info=True,
            )
            # エラーでも結果を保存（ユーザーに通知するため）
            try:
                async with async_session_maker() as session:
                    system_bot_user_id = await _ensure_system_bot_user(session)
                    error_reply = (
                        "Deep Research の実行中にエラーが発生しました。\n"
                        "再度お試しいただくこともできます。"
                    )
                    error_metadata = {
                        "deep_research": {
                            "requested_by_user_id": user_id,
                            "summary": "Deep Research の実行中にエラーが発生しました。",
                            "details": "再度お試しいただくこともできます。",
                            "is_cache_hit": False,
                        }
                    }
                    existing_log = await session.get(RawLog, uuid.UUID(research_log_id))
                    if existing_log:
                        existing_log.assistant_reply = error_reply
                        existing_log.metadata_analysis = error_metadata
                        existing_log.is_analyzed = True
                        existing_log.is_structure_analyzed = True
                        existing_log.is_processed_for_insight = True
                    else:
                        log = RawLog(
                            id=uuid.UUID(research_log_id),
                            user_id=system_bot_user_id,
                            thread_id=uuid.UUID(thread_id) if thread_id else None,
                            content=query,
                            content_type="deep_research",
                            assistant_reply=error_reply,
                            metadata_analysis=error_metadata,
                            is_analyzed=True,
                            is_structure_analyzed=True,
                            is_processed_for_insight=True,
                        )
                        session.add(log)
                    await session.commit()
            except Exception:
                logger.error(
                    f"Failed to save error log for {research_log_id}",
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
