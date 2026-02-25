"""
PLURA - Document Endpoints
Private RAG: ドキュメント管理API

- PDF アップロード → MinIO保存 → Celery で非同期処理
- ドキュメント一覧・詳細・削除
- Private RAG 検索
"""
import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, status
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.base import get_async_session
from app.models.user import User
from app.models.document import Document, DocumentStatus
from app.schemas.document import (
    DocumentResponse,
    DocumentListResponse,
    DocumentUploadResponse,
    DocumentStatusResponse,
    PresignedUrlResponse,
    PrivateRAGSearchResponse,
    PrivateRAGSearchResult,
)
from app.services.document_store import document_store
from app.services.layer1.private_rag import private_rag
from app.workers.document_tasks import process_document_task, delete_document_task

router = APIRouter()
logger = logging.getLogger(__name__)

# アップロード制限
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
ALLOWED_CONTENT_TYPES = {
    "application/pdf",
}


@router.post("/upload", response_model=DocumentUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    thread_id: Optional[str] = Query(None, description="完了通知ログを紐付けるチャットスレッドID"),
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
):
    """
    PDFドキュメントをアップロード

    - MinIOに原本を保存
    - Celeryタスクでテキスト抽出→チャンク分割→Embedding→Qdrant格納
    - thread_id が指定された場合、完了通知 RawLog にそのスレッドIDを付与する
    """
    # ファイル形式の検証
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"サポートされていないファイル形式です: {file.content_type}。PDF のみ対応しています。",
        )

    # ファイルサイズの検証
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"ファイルサイズが上限 ({MAX_FILE_SIZE // (1024*1024)}MB) を超えています。",
        )

    if len(content) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="空のファイルです。",
        )

    # MinIO にアップロード
    filename = file.filename or "document.pdf"
    object_key = document_store.generate_object_key(str(current_user.id), filename)

    uploaded = await document_store.upload_file(
        object_key=object_key,
        data=content,
        content_type=file.content_type or "application/pdf",
    )
    if not uploaded:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="ファイルのアップロードに失敗しました。",
        )

    # DB レコード作成
    doc = Document(
        user_id=current_user.id,
        filename=filename,
        content_type=file.content_type or "application/pdf",
        file_size=len(content),
        object_key=object_key,
        status=DocumentStatus.UPLOADING.value,
    )
    session.add(doc)
    await session.commit()
    await session.refresh(doc)

    # 非同期で PDF 処理タスクをキック
    try:
        process_document_task.delay(str(doc.id), thread_id=thread_id)
    except Exception as e:
        logger.error(f"Failed to queue document processing task: {e}")
        doc.status = DocumentStatus.ERROR.value
        doc.error_message = "処理タスクの開始に失敗しました。"
        await session.commit()

    return DocumentUploadResponse(
        id=doc.id,
        filename=doc.filename,
        file_size=doc.file_size,
        status=doc.status,
        message="アップロードを受け付けました。処理中です。",
    )


@router.get("/", response_model=DocumentListResponse)
async def list_documents(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
):
    """ドキュメント一覧を取得（自分のドキュメントのみ）"""
    count_result = await session.execute(
        select(func.count(Document.id)).where(Document.user_id == current_user.id)
    )
    total = count_result.scalar()

    offset = (page - 1) * page_size
    result = await session.execute(
        select(Document)
        .where(Document.user_id == current_user.id)
        .order_by(desc(Document.created_at))
        .offset(offset)
        .limit(page_size)
    )
    docs = result.scalars().all()

    return DocumentListResponse(
        items=[DocumentResponse.model_validate(doc) for doc in docs],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
):
    """特定のドキュメントを取得"""
    result = await session.execute(
        select(Document).where(
            Document.id == document_id,
            Document.user_id == current_user.id,
        )
    )
    doc = result.scalar_one_or_none()

    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    return DocumentResponse.model_validate(doc)


@router.get("/{document_id}/status", response_model=DocumentStatusResponse)
async def get_document_status(
    document_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
):
    """
    ドキュメントの処理状態を取得（ポーリング用軽量エンドポイント）

    フロントエンドから数秒おきにポーリングし、
    READY になった時点でユーザーに完了通知を表示する。
    """
    result = await session.execute(
        select(Document).where(
            Document.id == document_id,
            Document.user_id == current_user.id,
        )
    )
    doc = result.scalar_one_or_none()

    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    message_map = {
        DocumentStatus.UPLOADING.value: "アップロード中...",
        DocumentStatus.PROCESSING.value: "PDFを学習中...",
        DocumentStatus.READY.value: "PDFの学習が完了しました",
        DocumentStatus.ERROR.value: doc.error_message or "処理に失敗しました",
    }

    return DocumentStatusResponse(
        id=doc.id,
        filename=doc.filename,
        status=doc.status,
        message=message_map.get(doc.status, "処理中..."),
    )


@router.get("/{document_id}/presigned-url", response_model=PresignedUrlResponse)
async def get_presigned_url(
    document_id: uuid.UUID,
    expires_hours: int = Query(1, ge=1, le=24, description="URL有効期間（時間）"),
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
):
    """
    署名付きダウンロードURLを取得

    一時的なURLを発行してクライアントから直接MinIOのファイルにアクセスさせる。
    """
    from datetime import timedelta

    result = await session.execute(
        select(Document).where(
            Document.id == document_id,
            Document.user_id == current_user.id,
        )
    )
    doc = result.scalar_one_or_none()

    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    expires = timedelta(hours=expires_hours)
    url = await document_store.generate_presigned_url(doc.object_key, expires=expires)

    if not url:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="署名付きURLの生成に失敗しました。",
        )

    return PresignedUrlResponse(
        url=url,
        expires_in_seconds=int(expires.total_seconds()),
    )


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
):
    """
    ドキュメントを削除

    DB レコードを即座に削除し、MinIO + Qdrant のクリーンアップは非同期で実行
    """
    result = await session.execute(
        select(Document).where(
            Document.id == document_id,
            Document.user_id == current_user.id,
        )
    )
    doc = result.scalar_one_or_none()

    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    object_key = doc.object_key
    doc_id_str = str(doc.id)

    await session.delete(doc)
    await session.commit()

    # 非同期でストレージクリーンアップ
    try:
        delete_document_task.delay(doc_id_str, object_key)
    except Exception as e:
        logger.warning(f"Failed to queue delete task for {doc_id_str}: {e}")


@router.get("/search/rag", response_model=PrivateRAGSearchResponse)
async def search_documents(
    q: str = Query(..., min_length=1, description="検索クエリ"),
    limit: int = Query(5, ge=1, le=20),
    current_user: User = Depends(get_current_user),
):
    """
    Private RAG 検索

    ユーザーのアップロードドキュメントからセマンティック検索を実行
    """
    results = await private_rag.search(
        query=q,
        user_id=str(current_user.id),
        limit=limit,
    )

    return PrivateRAGSearchResponse(
        query=q,
        results=[
            PrivateRAGSearchResult(
                document_id=r["document_id"],
                filename=r["filename"],
                chunk_index=r["chunk_index"],
                text=r["text"],
                score=r["score"],
            )
            for r in results
        ],
        total=len(results),
    )
