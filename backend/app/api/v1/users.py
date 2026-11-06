"""
@file: app/api/v1/users.py
@description: 用户资料接口：查询与更新当前用户信息。
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.schemas.user import UserProfile, UserUpdateRequest

router = APIRouter(prefix="/users", tags=["用户"])


@router.get("/me", response_model=UserProfile, summary="获取当前用户信息")
def get_me(current_user: User = Depends(get_current_user)) -> User:
    """查询当前登录用户资料。

    @param current_user: 当前认证用户
    @return: 用户资料
    """
    return current_user


@router.put("/me", response_model=UserProfile, summary="更新当前用户信息")
def update_me(
    payload: UserUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> User:
    """更新当前用户昵称与头像。

    @param payload: 更新字段
    @param db: 数据库会话
    @param current_user: 当前认证用户
    @return: 更新后的用户资料
    """
    if payload.nickname is not None:
        current_user.nickname = payload.nickname
    if payload.avatar_url is not None:
        current_user.avatar_url = payload.avatar_url
    db.commit()
    db.refresh(current_user)
    return current_user
