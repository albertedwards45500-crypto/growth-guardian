"""
@file: app/services/advice.py
@description: 专业建议业务服务：分月龄指南匹配与 FAQ 关键词检索。
"""

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.advice import Faq, Guide


def match_guide(db: Session, age_months: int) -> Guide | None:
    """按月龄匹配对应的喂养指南。

    @param db: 数据库会话
    @param age_months: 宝宝月龄
    @return: 匹配的 Guide；无匹配时返回 None
    """
    return (
        db.query(Guide)
        .filter(Guide.month_start <= age_months, Guide.month_end >= age_months)
        .first()
    )


def search_faqs(
    db: Session,
    keyword: str | None = None,
    category: str | None = None,
) -> list[Faq]:
    """检索常见问题知识库。

    @param db: 数据库会话
    @param keyword: 关键词（匹配问题标题、解答、检索词）
    @param category: 问题分类
    @return: FAQ 列表
    """
    query = db.query(Faq)
    if category:
        query = query.filter(Faq.category == category)
    if keyword:
        like = f"%{keyword}%"
        query = query.filter(
            or_(Faq.question.like(like), Faq.answer.like(like), Faq.keywords.like(like))
        )
    return query.order_by(Faq.id.asc()).all()
