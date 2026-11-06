"""
@file: app/api/v1/advice.py
@description: 专业建议接口：分月龄喂养指南与常见问题检索。
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.advice import Faq, Guide
from app.models.user import User
from app.schemas.advice import FaqResponse, GuideResponse
from app.services.advice import match_guide, search_faqs

router = APIRouter(prefix="/advice", tags=["专业建议"])


@router.get("/guides", response_model=GuideResponse | None, summary="获取分月龄喂养指南")
def get_guide(
    month: int = Query(..., ge=0, le=36, description="宝宝月龄"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Guide | None:
    """按月龄匹配对应的喂养指南（立项书 4.4）。

    @param month: 宝宝月龄
    @param db: 数据库会话
    @param current_user: 当前认证用户
    @return: 匹配的指南；无匹配时返回 None
    """
    return match_guide(db, month)


@router.get("/faqs", response_model=list[FaqResponse], summary="检索常见问题")
def list_faqs(
    keyword: str | None = Query(None, description="检索关键词"),
    category: str | None = Query(None, description="问题分类"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Faq]:
    """检索常见喂养问题知识库。

    @param keyword: 关键词
    @param category: 分类过滤
    @param db: 数据库会话
    @param current_user: 当前认证用户
    @return: FAQ 列表
    """
    return search_faqs(db, keyword=keyword, category=category)
