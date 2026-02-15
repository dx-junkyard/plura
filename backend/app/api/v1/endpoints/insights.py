"""
PLURA - Insight Endpoints
Layer 3: Public Plaza API
"""
from datetime import datetime, timezone
from typing import Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func, desc, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_current_user_optional
from app.db.base import get_async_session
from app.models.user import User
from app.models.insight import InsightCard, InsightStatus
from app.schemas.insight import (
    InsightCardResponse,
    InsightCardListResponse,
    InsightCardUpdate,
    SharingProposal,
    SharingDecision,
)
from app.services.layer3.knowledge_store import knowledge_store

router = APIRouter()


@router.get("/", response_model=InsightCardListResponse)
async def list_insights(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    topic: Optional[str] = None,
    tag: Optional[str] = None,
    search: Optional[str] = None,
    session: AsyncSession = Depends(get_async_session),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """
    公開インサイト一覧を取得
    誰でも閲覧可能（認証オプショナル）
    """
    # 基本クエリ: 承認済みのみ
    query = select(InsightCard).where(InsightCard.status == InsightStatus.APPROVED)

    # トピックフィルタ
    if topic:
        query = query.where(InsightCard.topics.contains([topic]))

    # タグフィルタ
    if tag:
        query = query.where(InsightCard.tags.contains([tag]))

    # テキスト検索（タイトルとサマリー）
    if search:
        search_pattern = f"%{search}%"
        query = query.where(
            or_(
                InsightCard.title.ilike(search_pattern),
                InsightCard.summary.ilike(search_pattern),
            )
        )

    # 総数を取得
    count_query = select(func.count()).select_from(query.subquery())
    count_result = await session.execute(count_query)
    total = count_result.scalar()

    # ページネーション
    offset = (page - 1) * page_size
    query = query.order_by(desc(InsightCard.published_at)).offset(offset).limit(page_size)

    result = await session.execute(query)
    insights = result.scalars().all()

    return InsightCardListResponse(
        items=[InsightCardResponse.model_validate(insight) for insight in insights],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/my", response_model=InsightCardListResponse)
async def list_my_insights(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: Optional[InsightStatus] = None,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
):
    """自分のインサイト一覧を取得"""
    query = select(InsightCard).where(InsightCard.author_id == current_user.id)

    if status_filter:
        query = query.where(InsightCard.status == status_filter)

    # 総数を取得
    count_query = select(func.count()).select_from(query.subquery())
    count_result = await session.execute(count_query)
    total = count_result.scalar()

    # ページネーション
    offset = (page - 1) * page_size
    query = query.order_by(desc(InsightCard.created_at)).offset(offset).limit(page_size)

    result = await session.execute(query)
    insights = result.scalars().all()

    return InsightCardListResponse(
        items=[InsightCardResponse.model_validate(insight) for insight in insights],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/pending", response_model=list[SharingProposal])
async def get_pending_proposals(
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
):
    """
    承認待ちの共有提案を取得
    Sharing Broker からの提案
    """
    result = await session.execute(
        select(InsightCard).where(
            InsightCard.author_id == current_user.id,
            InsightCard.status == InsightStatus.PENDING_APPROVAL,
        ).order_by(desc(InsightCard.created_at))
    )
    insights = result.scalars().all()

    proposals = []
    for insight in insights:
        message = "あなたのこの経験は、チームの役に立つ可能性があります。この形式で共有しますか？"
        if insight.sharing_value_score >= 90:
            message = "特に価値の高い知見です。ぜひチームに共有しませんか？"
        elif insight.sharing_value_score >= 80:
            message = "多くの人に参考になりそうです。共有しますか？"

        proposals.append(
            SharingProposal(
                insight=InsightCardResponse.model_validate(insight),
                message=message,
            )
        )

    return proposals


@router.post("/decide", response_model=InsightCardResponse)
async def decide_sharing(
    decision: SharingDecision,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
):
    """
    共有の承認/拒否を決定
    """
    result = await session.execute(
        select(InsightCard).where(
            InsightCard.id == decision.insight_id,
            InsightCard.author_id == current_user.id,
        )
    )
    insight = result.scalar_one_or_none()

    if not insight:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Insight not found",
        )

    if insight.status not in [InsightStatus.DRAFT, InsightStatus.PENDING_APPROVAL]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Insight is not pending approval",
        )

    if decision.approved:
        insight.status = InsightStatus.APPROVED
        insight.published_at = datetime.now(timezone.utc)

        # ベクトルDBに保存
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
    else:
        insight.status = InsightStatus.REJECTED

    await session.commit()
    await session.refresh(insight)

    return InsightCardResponse.model_validate(insight)


@router.get("/{insight_id}", response_model=InsightCardResponse)
async def get_insight(
    insight_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """インサイト詳細を取得"""
    result = await session.execute(
        select(InsightCard).where(InsightCard.id == insight_id)
    )
    insight = result.scalar_one_or_none()

    if not insight:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Insight not found",
        )

    # 非公開のインサイトは作者のみ閲覧可能
    if insight.status != InsightStatus.APPROVED:
        if not current_user or insight.author_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Insight not found",
            )

    # 閲覧数をインクリメント（自分以外）
    if not current_user or insight.author_id != current_user.id:
        insight.view_count += 1
        await session.commit()

    return InsightCardResponse.model_validate(insight)


@router.post("/{insight_id}/thanks", status_code=status.HTTP_200_OK)
async def send_thanks(
    insight_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
):
    """
    インサイトに「ありがとう」を送る
    フィードバック機能
    """
    result = await session.execute(
        select(InsightCard).where(
            InsightCard.id == insight_id,
            InsightCard.status == InsightStatus.APPROVED,
        )
    )
    insight = result.scalar_one_or_none()

    if not insight:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Insight not found",
        )

    insight.thanks_count += 1
    await session.commit()

    return {"message": "Thanks sent!", "thanks_count": insight.thanks_count}
