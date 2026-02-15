"""
PLURA - Security Module
認証・認可とセキュリティ機能
"""
import secrets
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

logger = logging.getLogger(__name__)

# パスワードハッシュ設定
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ── 起動ごとにランダムな nonce を生成 ──
# コンテナ再起動で新しい値になるため、旧トークンは全て無効になる
_BOOT_NONCE = secrets.token_hex(16)
_EFFECTIVE_SECRET = settings.secret_key + ":" + _BOOT_NONCE
logger.info("Security boot nonce generated — all previous tokens invalidated")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """パスワードを検証"""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """パスワードをハッシュ化"""
    return pwd_context.hash(password)


def create_access_token(
    subject: str,
    expires_delta: Optional[timedelta] = None
) -> str:
    """JWTアクセストークンを生成"""
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.access_token_expire_minutes
        )

    to_encode = {
        "sub": subject,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }

    encoded_jwt = jwt.encode(
        to_encode,
        _EFFECTIVE_SECRET,
        algorithm=settings.algorithm
    )
    return encoded_jwt


def decode_access_token(token: str) -> Optional[str]:
    """JWTトークンをデコードしてユーザーIDを取得"""
    try:
        payload = jwt.decode(
            token,
            _EFFECTIVE_SECRET,
            algorithms=[settings.algorithm]
        )
        return payload.get("sub")
    except JWTError:
        return None
