"""
PLURA - Document Schemas
Private RAG: ドキュメント管理のリクエスト/レスポンススキーマ
"""
import uuid
from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, Field

from app.models.document import DocumentStatus


class DocumentResponse(BaseModel):
    """ドキュメントレスポンス"""
    id: uuid.UUID
    user_id: uuid.UUID
    project_id: Optional[uuid.UUID] = None
    filename: str
    content_type: str
    file_size: int
    status: str
    page_count: Optional[int] = None
    chunk_count: Optional[int] = None
    error_message: Optional[str] = None
    topics: Optional[List[str]] = None
    summary: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DocumentListResponse(BaseModel):
    """ドキュメント一覧レスポンス"""
    items: List[DocumentResponse]
    total: int
    page: int
    page_size: int


class DocumentUploadResponse(BaseModel):
    """アップロード成功レスポンス"""
    id: uuid.UUID
    filename: str
    file_size: int
    status: str
    message: str


class PresignedUrlResponse(BaseModel):
    """署名付きURLレスポンス"""
    url: str
    expires_in_seconds: int


class DocumentStatusResponse(BaseModel):
    """ドキュメント処理状態レスポンス（ポーリング用軽量版）"""
    id: uuid.UUID
    filename: str
    status: str
    message: str


class PrivateRAGSearchResult(BaseModel):
    """Private RAG 検索結果"""
    document_id: str
    filename: str
    chunk_index: int
    text: str
    score: float


class PrivateRAGSearchResponse(BaseModel):
    """Private RAG 検索レスポンス"""
    query: str
    results: List[PrivateRAGSearchResult]
    total: int
