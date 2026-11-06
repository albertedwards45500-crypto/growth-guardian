"""
@file: app/models/baby.py
@description: 宝宝档案表 ORM 模型。
"""

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Baby(Base):
    """宝宝档案模型。

    承载宝宝基础信息，成长/饮食/里程碑等记录均归属具体宝宝。
    """

    __tablename__ = "babies"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment="宝宝档案ID")
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, comment="所属用户ID"
    )
    name: Mapped[str] = mapped_column(String(50), comment="宝宝昵称")
    gender: Mapped[str | None] = mapped_column(String(10), nullable=True, comment="性别 male/female")
    birth_date: Mapped[date] = mapped_column(Date, comment="出生日期")
    avatar_url: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="头像地址")
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否默认档案")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间"
    )

    # 关联关系
    owner: Mapped["User"] = relationship(back_populates="babies")  # noqa: F821
    growth_records: Mapped[list["GrowthRecord"]] = relationship(  # noqa: F821
        back_populates="baby", cascade="all, delete-orphan"
    )
    milestones: Mapped[list["Milestone"]] = relationship(  # noqa: F821
        back_populates="baby", cascade="all, delete-orphan"
    )
    diet_records: Mapped[list["DietRecord"]] = relationship(  # noqa: F821
        back_populates="baby", cascade="all, delete-orphan"
    )
    allergies: Mapped[list["Allergy"]] = relationship(  # noqa: F821
        back_populates="baby", cascade="all, delete-orphan"
    )
    meal_plans: Mapped[list["MealPlan"]] = relationship(  # noqa: F821
        back_populates="baby", cascade="all, delete-orphan"
    )
