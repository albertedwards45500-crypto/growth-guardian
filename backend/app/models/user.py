"""
@file: app/models/user.py
@description: 用户表 ORM 模型。
"""

from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class User(Base):
    """用户账号模型。

    一个用户可关联多个宝宝档案（多宝宝支持，见立项书 4.1）。
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment="用户ID")
    phone: Mapped[str] = mapped_column(String(20), unique=True, index=True, comment="手机号（登录账号）")
    nickname: Mapped[str] = mapped_column(String(50), default="家长", comment="昵称")
    password_hash: Mapped[str] = mapped_column(String(128), comment="bcrypt 密码哈希")
    avatar_url: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="头像地址")
    is_active: Mapped[bool] = mapped_column(default=True, comment="是否启用")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间"
    )

    # 关联：一个用户拥有多个宝宝档案
    babies: Mapped[list["Baby"]] = relationship(  # noqa: F821
        back_populates="owner", cascade="all, delete-orphan"
    )
