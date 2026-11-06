"""
@file: app/models/recipe.py
@description: 食谱、收藏与辅食计划表 ORM 模型。
"""

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Recipe(Base):
    """辅食食谱模型。

    支持按月龄（suitable_age_min/max）、食材、营养标签筛选（立项书 4.3）。
    """

    __tablename__ = "recipes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment="食谱ID")
    title: Mapped[str] = mapped_column(String(100), comment="食谱名称")
    cover_url: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="封面图地址")
    suitable_age_min: Mapped[int] = mapped_column(Integer, default=6, comment="适合最小月龄")
    suitable_age_max: Mapped[int] = mapped_column(Integer, default=36, comment="适合最大月龄")
    # 食材清单 JSON：[{"name": "南瓜", "amount": "50g"}]
    ingredients: Mapped[list[Any]] = mapped_column(JSON, default=list, comment="食材清单JSON")
    # 制作步骤 JSON：["步骤1", "步骤2", ...]
    steps: Mapped[list[str]] = mapped_column(JSON, default=list, comment="制作步骤JSON")
    # 营养标签：["补铁", "易消化", "高钙"]
    nutrition_tags: Mapped[list[str]] = mapped_column(JSON, default=list, comment="营养标签JSON")
    # 适用说明/注意
    tips: Mapped[str | None] = mapped_column(Text, nullable=True, comment="食用注意与贴士")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否上架")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="创建时间")


class RecipeFavorite(Base):
    """食谱收藏模型（用户-食谱多对多）。

    D07 修复：通过 unique(user_id, recipe_id) 数据库级唯一约束保证
    同一用户对同一食谱仅存在一条收藏记录，支撑收藏接口幂等语义，
    并防止并发场景下重复收藏产生脏数据。
    """

    __tablename__ = "recipe_favorites"
    # 用户-食谱联合唯一：重复收藏在数据库层被拒绝（并发下接口层查重不可靠）
    __table_args__ = (
        UniqueConstraint("user_id", "recipe_id", name="uq_recipe_favorites_user_recipe"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment="收藏ID")
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, comment="用户ID"
    )
    recipe_id: Mapped[int] = mapped_column(
        ForeignKey("recipes.id", ondelete="CASCADE"), index=True, comment="食谱ID"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="收藏时间")


class MealPlan(Base):
    """一周辅食计划模型（按天×餐次绑定食谱）。

    D07 修复：通过 (baby_id, week_start, day_of_week, meal_type) 唯一约束
    保证同一宝宝同一周的同一天同餐次（即一个计划槽位）仅存在一条记录，
    防止"先删后插"重放或并发保存产生重复槽位数据。
    """

    __tablename__ = "meal_plans"
    # 计划槽位唯一：宝宝 × 周 × 星期 × 餐次 唯一（数据库层兜底）
    __table_args__ = (
        UniqueConstraint(
            "baby_id", "week_start", "day_of_week", "meal_type", name="uq_meal_plans_slot"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment="计划ID")
    baby_id: Mapped[int] = mapped_column(
        ForeignKey("babies.id", ondelete="CASCADE"), index=True, comment="宝宝ID"
    )
    week_start: Mapped[date] = mapped_column(Date, index=True, comment="计划周起始日期（周一）")
    day_of_week: Mapped[int] = mapped_column(Integer, comment="星期（0-6）")
    # 餐次：breakfast/lunch/dinner/snack
    meal_type: Mapped[str] = mapped_column(String(20), comment="餐次类型")
    recipe_id: Mapped[int | None] = mapped_column(
        ForeignKey("recipes.id", ondelete="SET NULL"), nullable=True, comment="食谱ID"
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="创建时间")

    baby: Mapped["Baby"] = relationship(back_populates="meal_plans")  # noqa: F821
    recipe: Mapped["Recipe"] = relationship()  # noqa: F821
