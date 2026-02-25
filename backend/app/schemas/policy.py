"""
PLURA - Policy Schemas
Policy Weaver のリクエスト/レスポンス Pydantic モデル
"""
import uuid
from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from app.models.policy import EnforcementLevel


# ────────────────────────────────────────
# LLM 抽出結果用の内部スキーマ
# ────────────────────────────────────────

class BoundaryConditions(BaseModel):
    """適用条件と例外条件"""
    applies_when: List[str] = Field(default_factory=list)
    except_when: List[str] = Field(default_factory=list)


class ExtractedPolicy(BaseModel):
    """LLM が非構造化ログから抽出した1件のポリシー"""
    dilemma_context: str = Field(..., description="解決したトレードオフやジレンマの背景")
    principle: str = Field(..., description="原則となるルール")
    boundary_conditions: BoundaryConditions = Field(default_factory=BoundaryConditions)


class ExtractionResult(BaseModel):
    """LLM 抽出タスクの結果"""
    policies: List[ExtractedPolicy] = Field(default_factory=list)
    raw_log_summary: Optional[str] = Field(
        default=None, description="入力ログの要約（デバッグ用）"
    )


# ────────────────────────────────────────
# API リクエストスキーマ
# ────────────────────────────────────────

class PolicyExtractRequest(BaseModel):
    """POST /policies/extract のリクエスト"""
    project_id: uuid.UUID = Field(..., description="対象プロジェクトID")


class PolicyOverrideRequest(BaseModel):
    """POST /policies/{id}/override のリクエスト"""
    reason_category: str = Field(
        ...,
        description="逸脱理由カテゴリ（テンプレ選択）",
        examples=["not_applicable", "outdated", "too_strict", "context_mismatch", "other"],
    )
    reason_detail: Optional[str] = Field(
        default=None,
        max_length=1000,
        description="自由記述による逸脱理由",
    )


# ────────────────────────────────────────
# API レスポンススキーマ
# ────────────────────────────────────────

class PolicyResponse(BaseModel):
    """ポリシーレスポンス"""
    id: uuid.UUID
    dilemma_context: str
    principle: str
    boundary_conditions: Dict
    enforcement_level: str
    ttl_expires_at: datetime
    is_strict_promoted: bool
    metrics: Dict
    source_project_id: Optional[uuid.UUID] = None
    created_by: Optional[uuid.UUID] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PolicyListResponse(BaseModel):
    """ポリシー一覧レスポンス"""
    items: List[PolicyResponse]
    total: int


class PolicyExtractAccepted(BaseModel):
    """抽出タスク受付レスポンス"""
    task_id: str = Field(..., description="Celery タスク ID")
    project_id: uuid.UUID
    message: str = "ポリシー抽出タスクを受け付けました"


class PolicyOverrideResponse(BaseModel):
    """Override 記録レスポンス"""
    policy_id: uuid.UUID
    override_count: int
    message: str = "Override を記録しました"
