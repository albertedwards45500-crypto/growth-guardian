"""
@file: app/api/v1/notifications.py
@description: 通知接口：分页列表、未读数、标记已读。
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.exceptions import NotFoundError
from app.models.notification import Notification
from app.models.user import User
from app.schemas.common import PageResult
from app.schemas.notification import NotificationResponse, UnreadCountResponse

router = APIRouter(prefix="/notifications", tags=["通知"])


@router.get("", response_model=PageResult[NotificationResponse], summary="获取通知列表")
def list_notifications(
    unread_only: bool = Query(False, description="仅查未读"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PageResult:
    """查询当前用户的通知列表（按创建时间倒序，D09 标准分页）。

    分页模式与食谱主列表对齐：page/page_size 由 Query 约束（ge=1、
    page_size<=100），非法参数由全局校验处理器统一转 42200；
    响应结构由裸列表变更为 {items, total, page, page_size}（复用 PageResult），
    原 unread_only 过滤、创建时间倒序排序与单条/全部已读行为均保留，
    原 limit 参数由 page/page_size 分页取代。

    @param unread_only: 是否仅返回未读
    @param page: 页码（从 1 开始）
    @param page_size: 每页条数（1-100）
    @param db: 数据库会话
    @param current_user: 当前认证用户
    @return: 分页通知结果（items 按创建时间倒序，id 倒序作为同秒稳定次序键）
    """
    query = db.query(Notification).filter(Notification.user_id == current_user.id)
    if unread_only:
        query = query.filter(Notification.is_read.is_(False))
    total = query.count()
    items = (
        # created_at 精度为秒，追加 id 倒序作为稳定次序键，保证分页不重不漏
        query.order_by(Notification.created_at.desc(), Notification.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return PageResult(items=items, total=total, page=page, page_size=page_size)


@router.get("/unread-count", response_model=UnreadCountResponse, summary="未读通知数")
def get_unread_count(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> UnreadCountResponse:
    """统计当前用户未读通知数（对应设计稿顶栏通知角标）。

    @param db: 数据库会话
    @param current_user: 当前认证用户
    @return: 未读数
    """
    count = (
        db.query(Notification)
        .filter(Notification.user_id == current_user.id, Notification.is_read.is_(False))
        .count()
    )
    return UnreadCountResponse(unread_count=count)


@router.patch("/{notification_id}/read", response_model=NotificationResponse, summary="标记已读")
def mark_read(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Notification:
    """将指定通知标记为已读。

    @param notification_id: 通知 ID
    @param db: 数据库会话
    @param current_user: 当前认证用户
    @return: 更新后的通知
    @raises NotFoundError: 通知不存在或不属于当前用户时抛出
    """
    notification = (
        db.query(Notification)
        .filter(Notification.id == notification_id, Notification.user_id == current_user.id)
        .first()
    )
    if notification is None:
        raise NotFoundError("通知不存在")
    notification.is_read = True
    db.commit()
    db.refresh(notification)
    return notification


@router.patch("/read-all", summary="全部标记已读")
def mark_all_read(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """将当前用户全部未读通知标记为已读。

    @param db: 数据库会话
    @param current_user: 当前认证用户
    @return: 更新数量
    """
    result = (
        db.query(Notification)
        .filter(Notification.user_id == current_user.id, Notification.is_read.is_(False))
        .update({Notification.is_read: True})
    )
    db.commit()
    return {"updated": result}
