"""
PLURA - Document Store (MinIO)
PDFファイルのオブジェクトストレージ管理
"""
import io
import logging
import uuid
from typing import Optional

from minio import Minio
from minio.error import S3Error

from app.core.config import settings

logger = logging.getLogger(__name__)


class DocumentStore:
    """
    MinIO ベースのドキュメントストレージ

    - PDFファイルのアップロード・ダウンロード・削除
    - バケットの自動初期化
    """

    def __init__(self):
        self._client: Optional[Minio] = None
        self._initialized = False

    def _get_client(self) -> Minio:
        """MinIO クライアントを取得（遅延初期化）"""
        if self._client is None:
            self._client = Minio(
                endpoint=settings.minio_endpoint,
                access_key=settings.minio_access_key,
                secret_key=settings.minio_secret_key,
                secure=settings.minio_secure,
            )
        return self._client

    async def initialize(self):
        """バケットの初期化（存在しなければ作成）"""
        if self._initialized:
            return

        try:
            client = self._get_client()
            if not client.bucket_exists(settings.minio_bucket_name):
                client.make_bucket(settings.minio_bucket_name)
                logger.info(f"Created MinIO bucket: {settings.minio_bucket_name}")
            self._initialized = True
        except Exception as e:
            logger.error(f"Failed to initialize MinIO: {e}", exc_info=True)

    def generate_object_key(self, user_id: str, filename: str) -> str:
        """ユーザーID + UUIDベースのオブジェクトキーを生成"""
        unique_id = uuid.uuid4().hex[:12]
        safe_filename = filename.replace("/", "_").replace("\\", "_")
        return f"{user_id}/{unique_id}_{safe_filename}"

    async def upload_file(
        self,
        object_key: str,
        data: bytes,
        content_type: str = "application/pdf",
    ) -> bool:
        """ファイルをMinIOにアップロード"""
        if not self._initialized:
            await self.initialize()

        try:
            client = self._get_client()
            client.put_object(
                bucket_name=settings.minio_bucket_name,
                object_name=object_key,
                data=io.BytesIO(data),
                length=len(data),
                content_type=content_type,
            )
            logger.info(f"Uploaded file to MinIO: {object_key} ({len(data)} bytes)")
            return True
        except S3Error as e:
            logger.error(f"Failed to upload to MinIO: {e}", exc_info=True)
            return False

    async def download_file(self, object_key: str) -> Optional[bytes]:
        """MinIOからファイルをダウンロード"""
        if not self._initialized:
            await self.initialize()

        try:
            client = self._get_client()
            response = client.get_object(
                bucket_name=settings.minio_bucket_name,
                object_name=object_key,
            )
            data = response.read()
            response.close()
            response.release_conn()
            return data
        except S3Error as e:
            logger.error(f"Failed to download from MinIO: {e}", exc_info=True)
            return None

    async def delete_file(self, object_key: str) -> bool:
        """MinIOからファイルを削除"""
        if not self._initialized:
            await self.initialize()

        try:
            client = self._get_client()
            client.remove_object(
                bucket_name=settings.minio_bucket_name,
                object_name=object_key,
            )
            logger.info(f"Deleted file from MinIO: {object_key}")
            return True
        except S3Error as e:
            logger.error(f"Failed to delete from MinIO: {e}", exc_info=True)
            return False


# シングルトンインスタンス
document_store = DocumentStore()
