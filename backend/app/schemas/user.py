"""
PLURA - User Schemas
ユーザー関連のスキーマ
"""
import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class UserBase(BaseModel):
    """ユーザー基底スキーマ"""

    email: EmailStr
    display_name: Optional[str] = None


class UserCreate(UserBase):
    """ユーザー作成スキーマ"""

    password: str = Field(..., min_length=8)


class UserUpdate(BaseModel):
    """ユーザー更新スキーマ"""

    display_name: Optional[str] = None
    avatar_url: Optional[str] = None


class UserResponse(UserBase):
    """ユーザーレスポンススキーマ"""

    id: uuid.UUID
    avatar_url: Optional[str] = None
    is_active: bool
    is_verified: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class UserLogin(BaseModel):
    """ログインリクエストスキーマ"""

    email: EmailStr
    password: str


class Token(BaseModel):
    """JWTトークンレスポンス"""

    access_token: str
    token_type: str = "bearer"
    user: UserResponse
