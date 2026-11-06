"""
@file: app/schemas/notification.py
@description: 通知相关 Pydantic Schema。
"""

from datetime import datetime

from pydantic import BaseModel, Field


class NotificationResponse(BaseModel):
    """通知响应模型。"""

    id: int
    notify_type: str
    title: str
    content: str
    is_read: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class UnreadCountResponse(BaseModel):
    """未读通知数响应模型。"""

    unread_count: int = Field(..., description="未读通知数")
