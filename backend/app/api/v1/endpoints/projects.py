"""
PLURA - Project Endpoints
Flash Team Formation: プロジェクト管理API
"""
import uuid
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.base import get_async_session
from app.models.user import User
from app.models.project import Project, ProjectStatus

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Schemas ──────────────────────────────────────────────────

class TeamMemberSchema(BaseModel):
    user_id: str
    display_name: str
    role: str
    avatar_url: Optional[str] = None


class ProjectCreateRequest(BaseModel):
    """TeamProposalCard の "Join Project" から呼ばれる"""
    name: str
    description: Optional[str] = None
    recommendation_id: Optional[str] = None
    team_members: List[TeamMemberSchema] = []
    topics: List[str] = []
    reason: Optional[str] = None


class ProjectResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    status: str
    created_by: str
    recommendation_id: Optional[str]
    team_members: list
    topics: list
    reason: Optional[str]
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class ProjectListItem(BaseModel):
    id: str
    name: str
    status: str
    topics: list
    member_count: int
    created_at: str


# ── Endpoints ────────────────────────────────────────────────

@router.post("/", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    request: ProjectCreateRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Flash Team プロジェクトを作成

    TeamProposalCard の "Join Project" ボタンで呼ばれる。
    AI 提案のメンバー構成をそのまま永続化する。
    """
    members_data = [m.model_dump() for m in request.team_members]

    project = Project(
        name=request.name,
        description=request.description,
        status=ProjectStatus.PROPOSED.value,
        created_by=current_user.id,
        recommendation_id=request.recommendation_id,
        team_members=members_data,
        topics=request.topics,
        reason=request.reason,
    )

    session.add(project)
    await session.commit()
    await session.refresh(project)

    logger.info(f"Project created: {project.id} by user {current_user.id}")

    return _to_response(project)


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    """プロジェクト詳細を取得"""
    result = await session.execute(
        select(Project).where(Project.id == project_id)
    )
    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    return _to_response(project)


@router.get("/", response_model=List[ProjectListItem])
async def list_my_projects(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    """自分が参加しているプロジェクト一覧"""
    result = await session.execute(
        select(Project)
        .where(Project.created_by == current_user.id)
        .order_by(Project.created_at.desc())
    )
    projects = result.scalars().all()

    return [
        ProjectListItem(
            id=str(p.id),
            name=p.name,
            status=p.status,
            topics=p.topics or [],
            member_count=len(p.team_members) if p.team_members else 0,
            created_at=p.created_at.isoformat(),
        )
        for p in projects
    ]


@router.patch("/{project_id}/status")
async def update_project_status(
    project_id: uuid.UUID,
    new_status: ProjectStatus,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    """プロジェクトのステータスを更新"""
    result = await session.execute(
        select(Project).where(Project.id == project_id)
    )
    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    if project.created_by != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the project creator can update status",
        )

    project.status = new_status.value
    await session.commit()

    return {"status": "ok", "new_status": new_status.value}


# ── Helpers ──────────────────────────────────────────────────

def _to_response(project: Project) -> ProjectResponse:
    return ProjectResponse(
        id=str(project.id),
        name=project.name,
        description=project.description,
        status=project.status,
        created_by=str(project.created_by),
        recommendation_id=project.recommendation_id,
        team_members=project.team_members or [],
        topics=project.topics or [],
        reason=project.reason,
        created_at=project.created_at.isoformat(),
        updated_at=project.updated_at.isoformat(),
    )
