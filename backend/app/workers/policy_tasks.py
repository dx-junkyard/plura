"""
PLURA - Policy Weaver Celery Tasks
heavy_queue で実行される重い LLM 処理タスク
"""
import asyncio
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.workers.celery_app import celery_app
from app.db.base import async_session_maker, engine
from app.models.policy import Policy, EnforcementLevel, DEFAULT_TTL_DAYS
from app.models.project import Project
from app.models.raw_log import RawLog
from app.services.layer3.policy_weaver import policy_weaver

logger = logging.getLogger(__name__)


def run_async(coro):
    """非同期関数を同期的に実行"""
    loop = asyncio.get_event_loop()
    if loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(asyncio.run, coro)
            return future.result()
    return loop.run_until_complete(coro)


@celery_app.task(bind=True, max_retries=2)
def extract_policies_task(self, project_id: str, user_id: str):
    """
    Policy Weaver: プロジェクトログからポリシーを抽出し DB に保存する。

    heavy_queue で実行される。
    """
    async def _extract():
        await engine.dispose()

        async with async_session_maker() as session:
            # 1. プロジェクトを取得
            project = await session.get(Project, uuid.UUID(project_id))
            if not project:
                logger.error("Project not found: %s", project_id)
                return {"status": "error", "message": "Project not found"}

            # 2. プロジェクトメンバーのユーザーIDを収集
            member_user_ids = []
            for member in (project.team_members or []):
                uid = member.get("user_id")
                if uid:
                    try:
                        member_user_ids.append(uuid.UUID(uid))
                    except ValueError:
                        continue

            # プロジェクト作成者も含める
            if project.created_by:
                member_user_ids.append(project.created_by)

            member_user_ids = list(set(member_user_ids))

            if not member_user_ids:
                logger.warning("No team members found for project: %s", project_id)
                return {"status": "skipped", "message": "No team members"}

            # 3. メンバーのログを取得（プロジェクト期間内）
            log_query = (
                select(RawLog)
                .where(
                    RawLog.user_id.in_(member_user_ids),
                    RawLog.created_at >= project.created_at,
                )
                .order_by(RawLog.created_at.asc())
                .limit(200)
            )
            result = await session.execute(log_query)
            raw_logs = result.scalars().all()

            if not raw_logs:
                logger.info("No logs found for project members: %s", project_id)
                return {"status": "skipped", "message": "No logs found"}

            # 4. ログのテキストを収集
            log_texts = [log.content for log in raw_logs if log.content]

            # 5. プロジェクトコンテキストを組み立て
            project_context = (
                f"プロジェクト名: {project.name}\n"
                f"説明: {project.description or '(なし)'}\n"
                f"トピック: {', '.join(project.topics) if project.topics else '(なし)'}\n"
                f"メンバー数: {len(member_user_ids)}"
            )

            # 6. LLM でポリシー抽出
            logger.info(
                "Starting policy extraction for project %s (%d logs)",
                project_id,
                len(log_texts),
            )
            extraction_result = await policy_weaver.extract_policies(
                logs=log_texts,
                project_context=project_context,
            )

            if not extraction_result.policies:
                logger.info("No policies extracted for project: %s", project_id)
                return {"status": "success", "policies_created": 0}

            # 7. 抽出結果を Policy レコードとして保存
            created_count = 0
            for extracted in extraction_result.policies:
                policy = Policy(
                    dilemma_context=extracted.dilemma_context,
                    principle=extracted.principle,
                    boundary_conditions=extracted.boundary_conditions.model_dump(),
                    enforcement_level=EnforcementLevel.SUGGEST.value,
                    ttl_expires_at=policy_weaver.compute_ttl_expiry(DEFAULT_TTL_DAYS),
                    is_strict_promoted=False,
                    metrics={
                        "override_count": 0,
                        "applied_count": 0,
                        "override_reasons": [],
                    },
                    source_project_id=project.id,
                    created_by=uuid.UUID(user_id),
                )
                session.add(policy)
                created_count += 1

            await session.commit()

            logger.info(
                "Policy extraction complete: project=%s, created=%d",
                project_id,
                created_count,
            )

            return {
                "status": "success",
                "project_id": project_id,
                "policies_created": created_count,
            }

    return run_async(_extract())


@celery_app.task
def expire_stale_policies_task():
    """
    TTL 切れポリシーの再評価期限をチェックし、
    enforcement_level を SUGGEST にダウングレードする。

    Celery Beat で毎日実行される。
    永久にルールが残らないようにする「ワクチンのような新陳代謝」。
    """
    async def _expire():
        await engine.dispose()

        async with async_session_maker() as session:
            now = datetime.now(timezone.utc)

            # TTL切れかつまだBLOCKに昇格されていないポリシーの
            # enforcement_level を SUGGEST にリセット
            result = await session.execute(
                update(Policy)
                .where(
                    Policy.ttl_expires_at <= now,
                    Policy.enforcement_level != EnforcementLevel.SUGGEST.value,
                )
                .values(enforcement_level=EnforcementLevel.SUGGEST.value)
                .returning(Policy.id)
            )
            expired_ids = [str(row[0]) for row in result.fetchall()]

            await session.commit()

            if expired_ids:
                logger.info(
                    "Expired %d stale policies: %s",
                    len(expired_ids),
                    expired_ids[:10],
                )
            else:
                logger.info("No stale policies to expire")

            return {
                "status": "success",
                "expired_count": len(expired_ids),
            }

    return run_async(_expire())
