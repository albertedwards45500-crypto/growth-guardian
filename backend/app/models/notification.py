"""
@file: app/models/notification.py
@description: 站内通知表 ORM 模型（对应设计稿顶栏通知按钮）。
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Notification(Base):
    """通知模型。

    用于疫苗接种提醒、测量提醒等个性化推送（立项书 4.1/4.4）。
    """

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment="通知ID")
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, comment="接收用户ID"
    )
    # 通知类型：milestone(里程碑)/reminder(提醒)/recommendation(建议)/system(系统)
    notify_type: Mapped[str] = mapped_column(String(20), default="system", comment="通知类型")
    title: Mapped[str] = mapped_column(String(100), comment="通知标题")
    content: Mapped[str] = mapped_column(Text, comment="通知内容")
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否已读")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="创建时间")
