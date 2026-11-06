"""
@file: app/models/diet.py
@description: 饮食记录与过敏食材表 ORM 模型。
"""

from datetime import date, datetime
from typing import Any

from sqlalchemy import JSON, Date, DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class DietRecord(Base):
    """饮食记录模型。

    覆盖三种记录类型（对应设计稿"喂奶/辅食"快捷入口）：
    - breast_milk 母乳：记录左右侧喂养时长（分钟）
    - formula 配方奶：记录奶量（ml）
    - solid_food 辅食：记录食材明细、宝宝反应、可选图片

    @param details: 类型化明细 JSON，如 {"left_minutes": 15, "right_minutes": 10}
    """

    __tablename__ = "diet_records"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment="记录ID")
    baby_id: Mapped[int] = mapped_column(
        ForeignKey("babies.id", ondelete="CASCADE"), index=True, comment="宝宝ID"
    )
    record_date: Mapped[date] = mapped_column(Date, index=True, comment="记录日期")
    record_type: Mapped[str] = mapped_column(String(20), comment="记录类型 breast_milk/formula/solid_food")
    # 类型化明细：母乳(左右分钟)、配方奶(奶量ml)、辅食(食材清单、反应、图片)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True, comment="类型化明细JSON")
    note: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="创建时间")

    baby: Mapped["Baby"] = relationship(back_populates="diet_records")  # noqa: F821


class Allergy(Base):
    """宝宝过敏/偏好食材模型。

    推荐食谱时自动规避过敏食材（立项书 4.2/4.3）。
    """

    __tablename__ = "allergies"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment="记录ID")
    baby_id: Mapped[int] = mapped_column(
        ForeignKey("babies.id", ondelete="CASCADE"), index=True, comment="宝宝ID"
    )
    ingredient: Mapped[str] = mapped_column(String(50), index=True, comment="食材名称")
    # 严重程度：mild(轻微)/moderate(中等)/severe(严重)
    severity: Mapped[str | None] = mapped_column(String(10), nullable=True, comment="严重程度")
    note: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="创建时间")

    baby: Mapped["Baby"] = relationship(back_populates="allergies")  # noqa: F821
