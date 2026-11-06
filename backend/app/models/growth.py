"""
@file: app/models/growth.py
@description: 成长记录与里程碑表 ORM 模型。
"""

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class GrowthRecord(Base):
    """生长记录模型（身高/体重/头围）。

    对应设计稿"最近测量"数据：体重 8.5kg、身高 72cm、头围 44cm。
    """

    __tablename__ = "growth_records"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment="记录ID")
    baby_id: Mapped[int] = mapped_column(
        ForeignKey("babies.id", ondelete="CASCADE"), index=True, comment="宝宝ID"
    )
    record_date: Mapped[date] = mapped_column(Date, index=True, comment="测量日期")
    weight_kg: Mapped[float | None] = mapped_column(Float, nullable=True, comment="体重（kg）")
    height_cm: Mapped[float | None] = mapped_column(Float, nullable=True, comment="身高（cm）")
    head_circumference_cm: Mapped[float | None] = mapped_column(Float, nullable=True, comment="头围（cm）")
    note: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="创建时间")

    baby: Mapped["Baby"] = relationship(back_populates="growth_records")  # noqa: F821


class Milestone(Base):
    """成长里程碑模型（翻身、独坐、爬行、行走等发育节点）。"""

    __tablename__ = "milestones"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment="里程碑ID")
    baby_id: Mapped[int] = mapped_column(
        ForeignKey("babies.id", ondelete="CASCADE"), index=True, comment="宝宝ID"
    )
    # 里程碑类型：roll_over(翻身) / sit(独坐) / crawl(爬行) / stand(站立) / walk(行走) / talk(说话) / ...
    milestone_type: Mapped[str] = mapped_column(String(30), comment="里程碑类型编码")
    name: Mapped[str] = mapped_column(String(50), comment="里程碑名称")
    achieved_at: Mapped[date] = mapped_column(Date, comment="达成日期")
    note: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="创建时间")

    baby: Mapped["Baby"] = relationship(back_populates="milestones")  # noqa: F821
