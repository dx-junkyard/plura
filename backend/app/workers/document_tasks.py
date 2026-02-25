"""
PLURA - Document Processing Tasks
Private RAG: PDF処理パイプライン（Celery タスク）

処理フロー:
  1. MinIO から PDF をダウンロード
  2. PyMuPDF でテキスト抽出
  3. チャンク分割
  4. Embedding → Qdrant 格納
  5. Document レコードを更新（chunk_count, page_count, status）
"""
import asyncio
import logging
import uuid
from typing import Optional, Tuple

from sqlalchemy import select

from app.workers.celery_app import celery_app
from app.db.base import async_session_maker, engine
from app.models.document import Document, DocumentStatus
from app.models.raw_log import RawLog, LogIntent
from app.services.document_store import document_store
from app.services.layer1.private_rag import private_rag, split_text_into_chunks

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


def _extract_pdf_text(pdf_bytes: bytes) -> Tuple[str, int]:
    """
    PyMuPDF でPDFからテキストを抽出

    Returns:
        (extracted_text, page_count)
    """
    import fitz  # PyMuPDF

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page_count = len(doc)
    text_parts = []

    for page in doc:
        text = page.get_text()
        if text.strip():
            text_parts.append(text)

    doc.close()
    return "\n\n".join(text_parts), page_count


@celery_app.task(bind=True, max_retries=2)
def process_document_task(self, document_id: str, thread_id: Optional[str] = None):
    """
    PDF処理パイプライン

    1. MinIO から PDF をダウンロード
    2. テキスト抽出（PyMuPDF）
    3. チャンク分割 → Embedding → Qdrant 格納
    4. Document ステータスを READY に更新 + 完了通知 RawLog を同一トランザクションで追加
    """
    async def _process():
        await engine.dispose()

        async with async_session_maker() as session:
            result = await session.execute(
                select(Document).where(Document.id == uuid.UUID(document_id))
            )
            doc = result.scalar_one_or_none()

            if not doc:
                logger.error(f"Document not found: {document_id}")
                return {"status": "error", "message": "Document not found"}

            # ステータスを処理中に更新
            doc.status = DocumentStatus.PROCESSING.value
            await session.commit()

            try:
                # Step 1: MinIO からダウンロード
                logger.info(f"Downloading PDF from MinIO: {doc.object_key}")
                pdf_bytes = await document_store.download_file(doc.object_key)
                if not pdf_bytes:
                    raise Exception("Failed to download PDF from MinIO")

                # Step 2: テキスト抽出
                logger.info(f"Extracting text from PDF: {document_id}")
                extracted_text, page_count = _extract_pdf_text(pdf_bytes)

                if not extracted_text.strip():
                    raise Exception("No text could be extracted from PDF")

                doc.page_count = page_count

                # Step 3: チャンク分割 → Qdrant 格納
                logger.info(
                    f"Splitting text into chunks: {document_id} "
                    f"({len(extracted_text)} chars, {page_count} pages)"
                )
                chunks = split_text_into_chunks(extracted_text)

                stored_count = await private_rag.store_chunks(
                    document_id=document_id,
                    user_id=str(doc.user_id),
                    filename=doc.filename,
                    chunks=chunks,
                )

                # Step 4: ステータスを READY に更新 + 完了通知 RawLog を追加
                # 同一トランザクションでコミットすることで、フロントエンドが
                # READY ステータスを検知した時点で必ず完了ログが存在することを保証する
                doc.chunk_count = stored_count
                doc.status = DocumentStatus.READY.value

                log_thread_id = uuid.UUID(thread_id) if thread_id else None
                completion_log = RawLog(
                    user_id=doc.user_id,
                    thread_id=log_thread_id,
                    content="[doc_ready]",
                    content_type="system_notification",
                    assistant_reply=(
                        f"📄 ドキュメント「{doc.filename}」の読み込みが完了しました！"
                        "「要約して」と指示したり、内容について質問してみてください。"
                    ),
                    intent=LogIntent.LOG,
                    is_analyzed=True,
                    is_processed_for_insight=True,
                    is_structure_analyzed=True,
                )
                session.add(completion_log)
                await session.commit()

                logger.info(
                    f"Document processing complete: {document_id}, "
                    f"pages={page_count}, chunks={stored_count}/{len(chunks)}"
                )
                logger.info(f"Completion notification logged for document: {document_id}")

                return {
                    "status": "success",
                    "document_id": document_id,
                    "page_count": page_count,
                    "chunk_count": stored_count,
                }

            except Exception as e:
                logger.error(
                    f"Error processing document {document_id}: {e}",
                    exc_info=True,
                )
                doc.status = DocumentStatus.ERROR.value
                doc.error_message = str(e)[:1000]
                await session.commit()
                return {"status": "error", "message": str(e)}

    return run_async(_process())


@celery_app.task(bind=True, max_retries=1)
def delete_document_task(self, document_id: str, object_key: str):
    """
    ドキュメント削除タスク

    1. Qdrant からチャンクを削除
    2. MinIO からファイルを削除
    """
    async def _delete():
        await engine.dispose()

        try:
            # Qdrant からチャンクを削除
            await private_rag.delete_document_chunks(document_id)

            # MinIO からファイルを削除
            await document_store.delete_file(object_key)

            logger.info(f"Document fully deleted: {document_id}")
            return {"status": "success", "document_id": document_id}
        except Exception as e:
            logger.error(
                f"Error deleting document {document_id}: {e}",
                exc_info=True,
            )
            return {"status": "error", "message": str(e)}

    return run_async(_delete())
