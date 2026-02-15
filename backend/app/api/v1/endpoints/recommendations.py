"""
MINDYARD - Recommendation Endpoints
Serendipity Matcher API
"""
from typing import Dict, List, Optional
import uuid

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.api.deps import get_current_user
from app.models.user import User
from app.services.layer3.serendipity_matcher import serendipity_matcher

router = APIRouter()


class RecommendationRequest(BaseModel):
    """レコメンデーションリクエスト"""
    current_input: str
    exclude_ids: Optional[List[str]] = None


class TeamMember(BaseModel):
    """チーム提案メンバー"""
    user_id: str
    display_name: str
    role: str
    avatar_url: Optional[str] = None


class RecommendationItem(BaseModel):
    """レコメンデーションアイテム"""
    id: str
    title: str
    summary: str
    topics: List[str]
    relevance_score: int
    preview: str
    category: Optional[str] = None  # "TEAM_PROPOSAL" for flash teams
    reason: Optional[str] = None
    team_members: Optional[List[TeamMember]] = None
    project_name: Optional[str] = None


class RecommendationResponse(BaseModel):
    """レコメンデーションレスポンス"""
    has_recommendations: bool
    recommendations: List[RecommendationItem]
    trigger_reason: str
    display_message: Optional[str] = None


@router.post("/", response_model=RecommendationResponse)
async def get_recommendations(
    request: RecommendationRequest,
    current_user: User = Depends(get_current_user),
):
    """
    入力中のテキストに基づいて関連インサイトを取得

    Serendipity Matcher による「副作用的」レコメンデーション
    - ユーザーが「検索」する前に関連情報を提示
    - 入力中/入力直後にトリガー
    """
    result = await serendipity_matcher.find_related_insights(
        current_input=request.current_input,
        user_id=current_user.id,
        exclude_ids=request.exclude_ids,
    )

    return RecommendationResponse(
        has_recommendations=result.get("has_recommendations", False),
        recommendations=[
            RecommendationItem(**rec) for rec in result.get("recommendations", [])
        ],
        trigger_reason=result.get("trigger_reason", "unknown"),
        display_message=result.get("display_message"),
    )


@router.get("/similar/{insight_id}")
async def get_similar_insights(
    insight_id: uuid.UUID,
    limit: int = Query(5, ge=1, le=20),
    current_user: User = Depends(get_current_user),
):
    """
    特定のインサイトに類似するインサイトを取得
    グラフ接続による関連知見の探索
    """
    from app.services.layer3.knowledge_store import knowledge_store

    # インサイトの情報を取得して類似検索
    # 実際の実装ではインサイトの内容を取得して検索
    # ここではシンプルにIDで検索をシミュレート
    return {
        "insight_id": str(insight_id),
        "similar_insights": [],
        "message": "Similar insights feature coming soon",
    }
