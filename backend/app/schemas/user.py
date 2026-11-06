"""
@file: app/schemas/user.py
@description: 用户信息相关 Pydantic Schema。
"""

from datetime import datetime

from pydantic import BaseModel, Field


class UserProfile(BaseModel):
    """用户信息响应模型。"""

    id: int
    phone: str
    nickname: str
    avatar_url: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class UserUpdateRequest(BaseModel):
    """用户资料更新请求模型。"""

    nickname: str | None = Field(None, max_length=50, description="昵称")
    avatar_url: str | None = Field(None, max_length=255, description="头像地址")
