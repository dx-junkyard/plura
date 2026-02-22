"""
PLURA - Policy Endpoints
Policy Weaver: ガバナンスルールの抽出・一覧・Override API
"""
import uuid
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.api.deps import get_current_user
from app.db.base import get_async_session
from app.models.user import User
from app.models.project import Project
from app.models.policy import Policy
from app.schemas.policy import (
    PolicyExtractRequest,
    PolicyExtractAccepted,
    PolicyListResponse,
    PolicyOverrideRequest,
    PolicyOverrideResponse,
    PolicyResponse,
)
from app.workers.policy_tasks import extract_policies_task

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post(
    "/extract",
    response_model=PolicyExtractAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
async def extract_policies(
    request: PolicyExtractRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    """
    指定プロジェクトのログからポリシーを非同期抽出する。

    heavy_queue で Celery タスクとして実行される。
    即座にタスク ID を返し、処理はバックグラウンドで行われる。
    """
    # プロジェクトの存在確認
    result = await session.execute(
        select(Project).where(Project.id == request.project_id)
    )
    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    # 非同期タスクをキューに投入（heavy_queue へルーティング）
    task = extract_policies_task.delay(
        project_id=str(request.project_id),
        user_id=str(current_user.id),
    )

    logger.info(
        "Policy extraction queued: project=%s, user=%s, task=%s",
        request.project_id,
        current_user.id,
        task.id,
    )

    return PolicyExtractAccepted(
        task_id=task.id,
        project_id=request.project_id,
    )


@router.get("/", response_model=PolicyListResponse)
async def list_policies(
    project_id: uuid.UUID | None = None,
    include_expired: bool = False,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    """
    有効な（TTL 切れでない）ポリシー一覧を取得する。

    Query params:
      - project_id: 特定プロジェクトのポリシーのみ取得
      - include_expired: True の場合は TTL 切れも含む
    """
    now = datetime.now(timezone.utc)

    query = select(Policy)

    if project_id:
        query = query.where(Policy.source_project_id == project_id)

    if not include_expired:
        query = query.where(Policy.ttl_expires_at > now)

    query = query.order_by(Policy.created_at.desc())

    result = await session.execute(query)
    policies = result.scalars().all()

    # 総数カウント（同じフィルタ条件）
    count_query = select(func.count(Policy.id))
    if project_id:
        count_query = count_query.where(Policy.source_project_id == project_id)
    if not include_expired:
        count_query = count_query.where(Policy.ttl_expires_at > now)

    count_result = await session.execute(count_query)
    total = count_result.scalar() or 0

    return PolicyListResponse(
        items=[PolicyResponse.model_validate(p) for p in policies],
        total=total,
    )


@router.post(
    "/{policy_id}/override",
    response_model=PolicyOverrideResponse,
)
async def override_policy(
    policy_id: uuid.UUID,
    request: PolicyOverrideRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    """
    ポリシーを Override（逸脱）した際の理由を記録する。

    Override はシステムの「主燃料」であり、
    蓄積されたフィードバックによってルールの境界条件が改善される。
    """
    result = await session.execute(
        select(Policy).where(Policy.id == policy_id)
    )
    policy = result.scalar_one_or_none()

    if not policy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Policy not found",
        )

    # メトリクスを更新
    metrics = dict(policy.metrics) if policy.metrics else {
        "override_count": 0,
        "applied_count": 0,
        "override_reasons": [],
    }

    metrics["override_count"] = metrics.get("override_count", 0) + 1
    override_reasons = metrics.get("override_reasons", [])
    override_reasons.append({
        "user_id": str(current_user.id),
        "category": request.reason_category,
        "detail": request.reason_detail,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    # 直近50件のみ保持（JSONB 肥大化防止）
    metrics["override_reasons"] = override_reasons[-50:]

    policy.metrics = metrics
    flag_modified(policy, "metrics")

    await session.commit()

    logger.info(
        "Policy overridden: policy=%s, user=%s, category=%s",
        policy_id,
        current_user.id,
        request.reason_category,
    )

    return PolicyOverrideResponse(
        policy_id=policy.id,
        override_count=metrics["override_count"],
    )
