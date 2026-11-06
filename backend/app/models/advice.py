"""
@file: app/models/advice.py
@description: 专业建议模块：分月龄喂养指南与常见问题知识库表 ORM 模型。
"""

from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Guide(Base):
    """分月龄喂养指南模型（立项书 4.4 专业建议）。"""

    __tablename__ = "guides"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment="指南ID")
    month_start: Mapped[int] = mapped_column(Integer, comment="适用起始月龄")
    month_end: Mapped[int] = mapped_column(Integer, comment="适用结束月龄")
    title: Mapped[str] = mapped_column(String(100), comment="指南标题")
    # 喂养要点正文（支持多段，用换行分隔）
    content: Mapped[str] = mapped_column(Text, comment="指南正文")
    # 食物建议 JSON：["高铁米粉", "南瓜泥", ...]
    food_suggestions: Mapped[list[str]] = mapped_column(JSON, default=list, comment="推荐食物清单JSON")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="创建时间")


class Faq(Base):
    """常见喂养问题模型（支持关键词检索）。"""

    __tablename__ = "faqs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment="问题ID")
    # 分类：allergy(过敏)/constipation(便秘)/picky(挑食)/milk(奶量)/...
    category: Mapped[str] = mapped_column(String(30), index=True, comment="问题分类")
    question: Mapped[str] = mapped_column(String(200), comment="问题标题")
    answer: Mapped[str] = mapped_column(Text, comment="解答内容")
    # 检索关键词，空格分隔
    keywords: Mapped[str | None] = mapped_column(String(200), nullable=True, comment="检索关键词")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="创建时间")
